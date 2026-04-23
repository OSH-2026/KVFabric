# KVFabric 小组研究报告：面向 LLM 推理服务的 KV Cache 生命周期管理


## 摘要

随着大语言模型逐步进入在线服务场景，推理系统不仅需要让模型能够运行，还需要在低时延、高吞吐和有限显存之间取得平衡。KV Cache 是自回归生成模型推理中的核心机制，它通过缓存历史 token 在各层 attention 中的 Key/Value 状态，避免每一步解码都重新计算完整历史上下文。KV Cache 显著降低了解码阶段计算量，但也将系统瓶颈转移到显存占用、动态分配、前缀复用、驱逐回收和多请求共享管理上。

现有工作已经分别证明了多个方向的价值：PagedAttention 通过 block/page 化 KV Cache 缓解连续分配碎片；vLLM Automatic Prefix Caching 通过 block hash、引用计数和 LRU 队列复用完全相同前缀；H2O、KVzip、AsymKV 等方法从 token 保留、压缩或合并角度降低存储与带宽压力。但这些方法大多针对某个局部环节，较少把 KV block 的分配、共享、分叉、驱逐和重建放在同一生命周期中协同建模。

KVFabric 的核心研究问题是：在面向 LLM serving 的场景中，能否把 KV Cache 视作完整生命周期对象，统一管理 allocation、reuse、fork、evict 和 rebuild，从而减少重复 prefill、降低错误驱逐后的重算成本，并提升共享前缀和局部分叉负载下的缓存利用率。本报告建议以官方 vLLM 作为短期基线和 Python 控制面原型平台，优先在 scheduler、KV cache manager、block pool、metadata 和 metrics 路径验证生命周期统计与共享感知驱逐；长期再将稳定策略抽象为以 C++ 为核心的可移植 KV Cache scheduler/runtime。

**关键词：** LLM 推理服务；KV Cache；PagedAttention；Prefix Caching；生命周期管理；共享感知驱逐；Copy-on-Write；vLLM；KVFabric

## 1. 资料来源与项目定位

本报告主要基于以下仓库材料整理：

- 原始小组材料：`investigation.pdf`，聚焦 KV Cache 现存问题、解决方案分类和研究空白。
- 原始小组材料：`LLM推理与KVCache分析.docx`，聚焦 LLM 推理流程、single-query attention、KV Cache 计算与存储分析、KV Cache 成立条件、生命周期管理和 CoW 增量复用设想。
- 平台对比材料：[vllm-vs-llamacpp.md](vllm-vs-llamacpp.md)，给出 vLLM 与 llama.cpp 的适用性判断。
- 项目可行性材料：[feasibility_report.md](../../reports/feasibility_report.md)，给出问题定义、技术路线、vLLM 切入点、实验设计与风险控制。
- 项目结构与基线材料：[README.md](../../../README.md)、[Architecture Overview](../../architecture/overview.md)、[vLLM Baseline](../../baseline/README.md)、[vLLM Baseline Workspace](../../../vllm_baseline/README.md)。

从仓库现状看，KVFabric 当前处于 `baseline bring-up / architecture freeze` 阶段。项目已经完成官方 vLLM 基线环境搭建，验证了 `Qwen/Qwen3.5-2B` 的 offline inference 和 OpenAI-compatible serving。短期目标不是从零实现一个新的推理引擎，而是在官方 vLLM 上读清 scheduler、prefix cache、PagedAttention 和 block manager 路径，先用 Python 控制面原型验证生命周期管理、共享感知驱逐与共享后分叉策略。长期目标则是抽象出可移植的 KV Cache scheduler/runtime，核心实现语言倾向 `C++17/20`。

## 2. LLM 推理过程与 KV Cache 基础

### 2.1 自回归推理流程

对于 decoder-only LLM，一次生成通常可以抽象为以下过程：

1. 输入 token 序列 `{T_1, ..., T_n}`，每个 token 是词表中的整数 ID。
2. Token preprocessing 将 token ID 转换为 embedding，得到 `{x_1^0, ..., x_n^0}`，其中上标 `0` 表示输入层。
3. 模型包含 `L` 层 Transformer block，每层输入和输出都是 token embedding 序列，最终得到 `{x_1^L, ..., x_n^L}`。
4. 使用最后一层最后一个 token 的表示 `x_n^L` 通过 `lm_head` 得到词表概率分布，再采样或选择下一个 token `T_{n+1}`。

整体流程可以写为：

```text
input tokens
  -> token processing
  -> transformer layer 1
  -> ...
  -> transformer layer L
  -> next token generation
  -> T_{n+1}
```

服务端推理通常分成两个阶段：

| 阶段 | 主要行为 | 主要瓶颈 | 与 KV Cache 的关系 |
| --- | --- | --- | --- |
| Prefill | 对输入 prompt 做完整前向计算 | 重复 prefill、首 token 时延、批处理组织 | 写入历史 token 的 K/V |
| Decode | 逐 token 生成后续文本 | KV 驻留、频繁调度、访存带宽、尾延迟 | 读取历史 K/V 并追加新 K/V |

Prefill 和 decode 不是两个孤立问题。它们共享同一批 KV block：prefill 决定缓存如何被创建，decode 决定缓存如何持续增长，调度与驱逐则决定缓存能否在后续请求中继续产生价值。

### 2.2 Single-Query Attention

当已有前 `n` 个 token 的中间状态被缓存后，生成第 `n+1` 个 token 时，每层只需要计算新 token 的输出。这可以看成 single-query attention。对某一层 `l` 和某个 head，可以写为：

```text
s_i = (W_Q * x_{n+1}^l)^T * (W_K * x_i^l), 1 <= i <= n+1

y_h = sum_i softmax(s_i) * W_V * x_i^l

x_{n+1}^{l+1} = Concat(y_1, ..., y_H)
```

其中 `W_Q`、`W_K`、`W_V` 是 Q/K/V 投影矩阵，`H` 是 attention heads 数量。LayerNorm、FFN 等操作对每个 token 位置独立执行，不改变 KV Cache 的核心结论，因此这里不展开。

### 2.3 KV Cache 的核心思想

如果只保存历史 token 的 `x_i^l`，则每一步 decode 都需要重新计算 `W_K * x_i^l` 和 `W_V * x_i^l`。KV Cache 的思想是直接缓存投影后的 Key 和 Value：

```text
K_i^l = W_K * x_i^l
V_i^l = W_V * x_i^l
```

后续生成新 token 时，只需为新 token 计算 Query、Key、Value，再读取历史 K/V 完成 attention。它本质上是用更多显存换取更低的 decode 计算量。

### 2.4 Cache 类型对比

原始材料比较了三类 cache：

- `x cache`：缓存每层历史 token 的 hidden state `x_i^l`。
- `k cache + v cache`：缓存投影后的 Key 和 Value。
- `s cache + v cache`：利用矩阵乘法性质预计算与 score 相关的中间项，同时缓存 Value。

设：

- `D` 为 token embedding 维度。
- `d` 为每个 head 的维度。
- `D = H * d`。
- `n` 为已缓存 token 数。

每个 head 的解码阶段开销可以概括为：

| Cache 类型 | 每条 cache 存储 | 建立 cache 的预计算 | 生成下一个 token 的计算量 |
| --- | --- | --- | --- |
| `x cache` | `D` | `0` | `[D d + (n+1)(2D d + 2d)] H` |
| `k cache + v cache` | `2d` | `2D d` | `[3D d + 2(n+1)d] H` |
| `s cache + v cache` | `D + d` | `3D d` | `[3D d + (n+1)(D+d)] H` |

`x cache` 和 KV Cache 的总计算量本质一致，区别在于是否把 K/V 投影提前做掉。KV Cache 在 decode 热路径中与历史长度 `n` 相关的项为 `O(n d)`，而 `x cache` 需要对历史 token 重做 K/V 投影，与 `n` 相关的项为 `O(n D d)`。在长上下文和多 head 场景下，`D` 远大于 `d`，因此 KV Cache 的 decode 延迟优势非常明显。

需要注意，`x cache` 从纯存储角度并不一定总是更大，因为 `x_i^l` 可被所有 heads 共享，而 KV Cache 对每个 head 保存 K/V。但真实推理系统选择 KV Cache 的根本原因是 decode 热路径效率，而不是单看每条 cache 的字节数。

### 2.5 KV Cache 的成立条件

KV Cache 依赖一个关键条件：模型必须具有因果性。向序列末尾追加新 token 后，前 `n` 个位置的输出应保持不变：

```text
hat{x}_i^{l+1} = x_i^{l+1}, 1 <= i <= n
```

GPT 类 decoder-only 模型使用 causal mask，满足这个条件；BERT 类 encoder 模型由于双向 attention 不满足这个条件，因此不能直接使用同样意义上的自回归 KV Cache。

还要额外关注输入预处理层。Token embedding 通常包括 word embedding 和 positional embedding。如果某些位置编码机制在追加 token 后会重新调整整个序列中已有 token 的位置表示，则旧 token 的输入 embedding 会改变，进而破坏 KV Cache 的正确性。因此，KV Cache 的工程实现不仅依赖 Transformer block 的 causal mask，也依赖输入预处理和位置编码机制是否稳定。

### 2.6 KV Cache 显存规模

对于 decoder-only 模型，单个请求长度为 `T` 时，KV Cache 近似占用：

```text
M_KV_req ~= 2 * L * H_kv * D_head * T * s
```

其中 `L` 为层数，`H_kv` 为 KV heads 数，`D_head` 为每个 head 维度，`s` 为单个元素字节数。并发请求总开销约为：

```text
M_KV_total ~= sum_r 2 * L * H_kv * D_head * T_r * s
```

这个式子说明三件事：

- KV Cache 对上下文长度近似线性增长。
- 并发请求的 KV Cache 占用会直接叠加。
- 在模型参数已经加载后，真正限制服务并发能力的往往是剩余可用于 KV Cache 的显存空间。

## 3. KV Cache 现存问题

### 3.1 上下文长度导致显存线性增长

随着 prompt 和生成长度增加，KV Cache 会持续膨胀。在长文档问答、多轮对话、长链条推理和高并发服务中，这会导致最大上下文受限、batch size 下降、吞吐降低和 OOM 风险上升。

代表性思路包括 H2O、KVzip、CentroidKV、AsymKV 等。它们通过 token 选择、query-agnostic 压缩、聚类或非对称压缩降低 KV 体积，但通常需要在压缩率、质量、适应性和实现复杂度之间权衡。

### 3.2 Decode 阶段访存压力成为瓶颈

Decode 每生成一个 token 都要访问历史 K/V。上下文越长，读取量越大，系统容易从算力瓶颈转向带宽瓶颈，表现为 token latency 上升、decode tokens/s 下降、GPU 利用率不高但服务仍然变慢。

压缩、量化和 selective loading 可以减少访问量，但可能引入精度损失、长期生成误差累积和 kernel/framework 耦合问题。

### 3.3 淘汰或压缩会影响生成质量

若驱逐了真正重要的历史信息，模型可能忘记早期事实、偏离多轮任务、降低长上下文问答准确率。ReST-KV、KeyDiff、ContextKeeper 等方法尝试重新定义 token 重要性或做 head-specific 保留，但重要性定义仍不统一，跨任务稳定性也有待验证。

### 3.4 单查询最优不等于多查询最优

很多策略默认只服务当前 query，但真实服务中常见多轮对话、多 query 共享上下文、模板化 prompt、围绕同一文档的多次问答。单次最优的缓存保留策略未必适合后续请求。KVzip 的 query-agnostic 压缩、SCBench 的生命周期评测、Prefix Caching 的共享前缀复用，都在不同角度回应这一问题，但多 query 共享上下文下的最优策略仍未完全明确。

### 3.5 动态分配带来碎片与管理开销

KV Cache 在服务中动态增长和释放。连续大块分配容易出现内部碎片、显存浪费和分配回收开销。PagedAttention/vLLM 将 KV 按 block/page 管理，按需分配，显著降低碎片；vAttention 则从虚拟内存角度尝试降低分页管理对 attention kernel 的侵入。但 block/page 化也引入了 block table、slot mapping、free queue 和元数据维护复杂度。

### 3.6 前缀复用不足导致重复 prefill

真实服务中大量请求共享 system prompt、模板化指令、RAG 输入模板或多轮对话公共历史。如果系统不能复用这些前缀，就会重复 prefill、重复写入 KV、拉高 TTFT 并降低吞吐。

vLLM Automatic Prefix Caching 已通过 block hash、引用计数、free queue 和 LRU 管理实现完全相同前缀复用。但其主要受益场景仍是 exact prefix match，对于局部分叉、模板中间槽位变化、chunk 级部分重叠等模式，复用能力有限。

### 3.7 层、头、K/V 与任务场景存在异质性

不同层、不同 heads、不同任务类型对历史上下文依赖差异明显。统一预算或统一驱逐策略难以适配所有情况。ContextKeeper、AsymKV、TailorKV、SCBench 等工作说明了 layer/head/scene-aware 管理的潜力，但联合策略的开销控制和收益稳定性仍是挑战。

### 3.8 生命周期管理缺乏统一协同

现有优化常被拆成单点：

- 分配优化，如 PagedAttention。
- 共享优化，如 Prefix Caching 或 RadixAttention 类思想。
- 驱逐或压缩优化，如 H2O、SnapKV、ScissorHands 等。

但真实系统中，KV Cache 的生命周期包括创建、填充、使用、共享、分叉、驱逐、回收和重建。分配粒度影响共享机会，共享状态影响驱逐价值，驱逐结果又影响后续重算和分配压力。缺乏统一生命周期框架，是 KVFabric 最关心的研究空白。

## 4. 相关方案分类与研究空白

### 4.1 Token 级方法

Token 级方法决定保留哪些 token 的 KV。代表方法包括 H2O、ReST-KV、KeyDiff、ContextKeeper。

优点是思路直接，便于量化压缩率和质量变化；不足是容易忽视系统实现复杂度，在多 query 和共享上下文场景下稳定性不足。

### 4.2 压缩与合并方法

压缩与合并方法减少 KV 存储和访存量。代表方法包括 KVzip、AsymKV、CentroidKV、TurboQuant 和 WKVQuant。

优点是压缩率较高，可能兼顾性能与质量；不足是实现复杂，误差分析困难，对 kernel 和 framework 兼容性要求较高。

### 4.3 系统级方法

系统级方法从服务系统角度优化 KV 分配、共享、回收和评测。代表方法包括 vLLM PagedAttention、vLLM Prefix Caching、vAttention 和 SCBench。

优点是贴近真实部署，容易形成完整系统课题；不足是工程复杂度高，需要清晰的实验设计和可控改造边界。

### 4.4 明确研究空白

结合现有材料，本项目关注以下空白：

1. 近似前缀、分叉前缀和 chunk 级共享仍不充分。
2. 多 query、共享上下文、多轮场景下的缓存策略仍缺少统一模型。
3. layer/head/K/V/scene-aware 的联合 KV 管理仍不成熟。
4. 分配、复用、驱逐缺乏统一生命周期框架。
5. 除显存与吞吐外，还需要关注命中率、驱逐 regret、重算比例、生命周期行为和长生成稳定性。

## 5. KVFabric 的核心研究方向

### 5.1 统一生命周期管理

KVFabric 建议把每个 KV block 看成一个生命周期对象，而不是静态显存片段。一个 block 可以经历以下状态：

```text
Create
  -> Populate
  -> Share
  -> Fork
  -> Copy-on-Write
  -> Cooling
  -> Evict
  -> Rebuild
```

这些状态需要满足基本正确性约束：

- 只有已填满且内容稳定的 full block 才适合作为可哈希、可共享对象。
- 未填满的尾块通常处于构建中状态，不应直接进入共享池。
- 多请求共享的 block 应默认视为逻辑只读。
- 只有 `ref_cnt == 0` 的 block 才能进入真正驱逐候选集合。
- block 被驱逐后，其 hash、热度、共享关系和分叉统计也必须同步失效。

### 5.2 生命周期元数据

KVFabric 的第一版元数据可以采用 side table 方式外挂在 vLLM block manager 旁边，避免一开始大幅改动核心对象结构。建议字段包括：

| 字段 | 含义 | 更新时机 | 作用 |
| --- | --- | --- | --- |
| `block_id` | 物理 block 标识 | 创建时 | 连接 vLLM 现有 block |
| `block_hash` | 内容 hash | full block 稳定时 | 支持 prefix/chunk 命中 |
| `ref_cnt` | 当前引用数 | 复用、释放、回收时 | 判定是否可驱逐 |
| `last_access_ts` | 最近访问时间 | 命中、引用、追加时 | 时间局部性 |
| `hit_count` | 历史复用次数 | 前缀命中时 | 长期热度估计 |
| `share_degree` | 共享深度 | 新请求复用或结束时 | 识别热点共享块 |
| `prefix_depth` | 位于前缀中的相对位置 | block 完成时 | 前段前缀更值得保留 |
| `recompute_cost` | 驱逐后重建代价 | prefill 完成或统计更新时 | 支持重算感知驱逐 |
| `share_state` | `Private`、`Shared`、`Forked` 等 | 共享和分叉时 | 描述生命周期状态 |
| `branch_factor` | 后续分叉数量 | 分叉形成时 | 识别共享后分叉结构 |

### 5.3 分配、复用与驱逐联动

新请求到来时，分配路径不应直接申请新 block，而应先查询全局 hash/radix 索引，检查是否存在可复用 block。若命中，则新请求的逻辑 block table 指向已有物理 block，并增加 `ref_cnt`，同时刷新访问热度和命中统计。

这意味着共享 block 不是“命中后静态保留”的对象，而是继续参与生命周期决策。其 `share_degree`、`hit_count`、`prefix_depth`、`recompute_cost` 等信息会影响后续驱逐优先级。

### 5.4 生命周期感知驱逐

传统 LRU 只看最近使用时间，无法表达 KV block 的长期价值。KVFabric 建议引入轻量综合评分：

```text
KeepScore(b) =
  w1 * Heat(b)
+ w2 * Share(b)
+ w3 * Reuse(b)
+ w4 * PrefixPos(b)
+ w5 * Recompute(b)
```

其中：

- `Heat` 表示近期访问热度。
- `Share` 表示当前共享程度。
- `Reuse` 表示历史命中频率。
- `PrefixPos` 表示前缀位置价值，越靠近系统提示或公共模板前段通常越重要。
- `Recompute` 表示驱逐后重建代价。

驱逐时优先淘汰 `KeepScore` 较低且 `ref_cnt == 0` 的 block。为了控制开销，可采用二阶段策略：

1. 继续复用 vLLM 当前 free queue 或 LRU 队列做粗筛。
2. 只在显存水位接近阈值时，对候选子集计算生命周期分数。

这样可以避免每次 token 访问都做全局重排，又能在关键驱逐时刻引入共享和重算信息。

## 6. 基于 Copy-on-Write 的增量前缀复用

### 6.1 问题背景

现有 prefix caching 常要求 token 前缀完全一致。但真实模板化 prompt 往往只有局部差异。例如：

```text
你是一个专业的法律顾问。用户：{name}，你的问题是：{question}。请用中文回答。
```

不同请求可能共享模板前后文，只在 `{name}` 和 `{question}` 槽位不同。若系统只能识别完整前缀相同，则大量可复用内容会失效。

### 6.2 Chunk 级哈希与共享

可以将输入按语义边界或固定 token block 切成 chunk，并对每个 chunk 独立计算 hash。若两个请求的某些 chunk 完全相同，则对应 KV block 可以共享物理存储，而不要求整段 prompt 完全一致。

第一版实现不应强行追求复杂的语义近似匹配。更稳妥的层次是：

- `L0`：沿用 vLLM exact prefix block hash，建立可靠基线。
- `L1`：显式记录共享链和分叉链，实现共享后分叉的生命周期统计与驱逐优化。
- `L2`：探索 chunk 级部分重叠和近似复用，作为后续扩展。

### 6.3 CoW 分叉流程

当 block 被多个请求共享时，可以将其视为只读。若某请求需要向共享 block 追加不同内容，则触发 CoW：

1. 从物理 block pool 申请新 block。
2. 将原共享 block 中已有内容复制到新 block。
3. 将触发写入的请求重新映射到新 block。
4. 在新 block 中继续追加分叉内容。
5. 原 block 的 `ref_cnt` 减一，若归零则进入可驱逐候选。

这个过程借鉴操作系统 `fork()` 后的写时复制思想。其价值在于，多个请求共享相同上下文时不需要提前复制，只有真正分叉写入时才付出 block 级复制成本。

### 6.4 与生命周期管理的关系

CoW 增量复用依赖生命周期元数据：

- `ref_cnt` 决定是否共享以及是否可驱逐。
- `share_state` 决定 block 是 private、shared 还是 forked。
- `branch_factor` 描述共享后分叉结构。
- `recompute_cost` 和 `prefix_depth` 帮助判断原始共享块与分叉副本谁更值得保留。

因此，CoW 不应作为独立功能孤立实现，而应建立在统一 metadata 和状态机之上。

## 7. vLLM 与 llama.cpp 选型结论

### 7.1 项目对基础框架的要求

本项目需要的不是单纯“能跑模型”的推理程序，而是可承载缓存系统策略实验的服务框架。理想平台应具备：

- 显式 KV block/page 管理。
- 可观察元数据，如引用计数、访问时间、共享状态。
- 多请求调度能力。
- prefix caching 或相近机制。
- 驱逐/回收入口。
- 清晰的 scheduler、cache manager、block pool 等代码边界。
- 可采集命中率、延迟、吞吐、显存、重算开销等指标。

### 7.2 对比结论

| 维度 | vLLM | llama.cpp | 对 KVFabric 的含义 |
| --- | --- | --- | --- |
| 系统定位 | 服务端高吞吐 LLM serving | 轻量本地推理与广泛硬件适配 | 本项目问题域更接近 vLLM |
| KV 抽象 | PagedAttention，block/page 化管理 | 更偏执行上下文内部缓存 | vLLM 更适合生命周期建模 |
| Prefix reuse | 已有 Automatic Prefix Caching | 需要自行补共享基础设施 | vLLM 可直接进入核心问题 |
| 调度能力 | 多请求调度和 serving 路径成熟 | 有 server，但服务级缓存治理不是主线 | vLLM 更适合服务级实验 |
| 改造成本 | 源码复杂，但对象基础合适 | 入门轻，但若支撑本项目需大量补基础设施 | 总成本 vLLM 更经济 |
| 推荐角色 | 主研究平台 | 辅助对照、边缘侧参考 | 采用 vLLM 为主、llama.cpp 为辅 |

结论是：KVFabric 短期应优先选择 vLLM 作为主研究平台。llama.cpp 适合作为轻量对照、CPU 场景补充或迁移边界讨论，不适合作为统一生命周期管理的主实现平台。

## 8. 基于 vLLM 的实现基础与切入点

### 8.1 仓库内已完成基线

当前仓库的 `vllm_baseline/` 已经提供：

- 环境安装脚本：`scripts/setup_venv.sh`
- 模型下载脚本：`scripts/download_model.sh`
- offline smoke test：`examples/offline_smoke.py`
- online serving 启停与验证：`serve_local.sh`、`verify_server.sh`、`stop_server.sh`
- 模型预设：`Qwen/Qwen3.5-2B` 和 `Qwen/Qwen3-8B`

已验证环境包括 `Ubuntu 24.04.1 LTS on WSL2`、`Python 3.12.3`、`NVIDIA RTX 4070 Laptop GPU 8 GiB`、`PyTorch 2.10.0+cu129` 和 `vLLM 0.19.0`。默认小模型已经完成 offline 和 online smoke test。

### 8.2 短期 vLLM Python 控制面改造范围

结合架构文档和可行性报告，短期若修改 vLLM，应优先关注：

- `vllm/v1/core/sched/scheduler.py`：请求调度、prefix hit 后的 token 计算状态、preemption 和分配调用入口。
- `vllm/v1/core/kv_cache_manager.py`：`get_computed_blocks`、`can_fit_full_sequence`、`allocate_slots`、`free`、`evict_blocks` 等主接口。
- `vllm/v1/core/block_pool.py`：`BlockPool`、free block queue、block hash 映射和缓存块驱逐入口。
- `vllm/v1/core/kv_cache_utils.py`：`KVCacheBlock`、block hash、free queue 等基础元数据结构。
- `vllm/v1/core/single_type_kv_cache_manager.py` 与 `kv_cache_coordinator.py`：多 KV cache group 下的分配、命中、释放和 skipped block 处理。
- `vllm/v1/metrics/`：prefix hit、block lifetime、eviction、recompute 等观测指标。

第一阶段不建议直接改：

- C++/CUDA attention kernel。
- 底层 KV 物理布局。
- slot mapping 语义。
- 自定义算子。

只有当功能必须改变 block 内存布局、kernel 读写方式、跨 block copy 语义或真正 in-kernel CoW 写入路径时，才进入 C++/CUDA 修改范围。

### 8.3 建议最小原型顺序

1. **观测层**：在 `KVCacheManager` 和 `BlockPool` 交界处记录命中、共享、驱逐、重建事件，形成生命周期日志。
2. **元数据层**：通过 side table 维护 `ref_cnt` 之外的生命周期字段，避免第一步大幅改 vLLM 核心类。
3. **策略层**：在 block 回收路径引入二阶段共享感知驱逐，对候选 block 计算 `KeepScore`。
4. **分叉层**：在前两层稳定后，向 scheduler 暴露共享链和分叉链信息，逐步验证共享后分叉场景。

这种顺序的好处是每一步都有可独立验证的中间成果。即使 chunk 级 CoW 未完全落地，生命周期统计和共享感知驱逐也能形成完整研究闭环。

## 9. 目标系统架构

KVFabric 的长期架构可概括为：

```text
Frontend / Engine Adapters
  -> KVFabric Scheduler Core
  -> Metadata & Block Table
  -> Backend Abstraction
```

各层职责如下：

- **Frontend / Engine Adapters**：短期接入 vLLM，后续可扩展到其他 serving 框架。
- **Scheduler Core**：负责 allocate、reuse、fork、evict 等策略决策。
- **Metadata & Block Table**：维护 ref count、share state、access history、recompute cost、prefix/chunk identity。
- **Backend Abstraction**：封装 CUDA、ROCm、CPU 或未来后端的物理存储和 copy/write 操作。

短期实现可以是 vLLM 内部的 Python side table 与 manager 扩展；长期则应把稳定策略抽象为 C++ runtime，避免核心调度逻辑永久绑定在某个 Python serving 框架内部。

## 10. 实验设计与评估指标

### 10.1 工作负载

建议构造以下请求集：

| 负载类型 | 共享模式 | 主要观察点 |
| --- | --- | --- |
| 完全共享前缀 | 多请求共享相同 system prompt 或模板开头 | prefix hit、TTFT 改善 |
| 单点分叉 | 前半段共享，固定位置后分叉 | 共享链保留价值、尾块分配 |
| 逐步分叉 | 多个阶段逐渐分化 | 分叉结构对驱逐的影响 |
| Chunk 级部分重叠 | 局部片段相同但不构成严格前缀 | chunk 级复用潜力 |
| 混合冷热负载 | 热点模板和长尾请求共存 | 驱逐 regret、缓存稳定性 |
| 长上下文压力 | 少量共享、上下文较长 | 显存压力、回收频率 |

本地 8GB 显存环境可先使用 `Qwen/Qwen3.5-2B`，将 `max_model_len` 控制在 `1024` 到 `2048`，并通过增加共享前缀比例和请求到达模式放大策略差异。更高并发和更长上下文可在更大显存服务器上复跑关键实验。

### 10.2 对比组

至少应包含：

- 官方 vLLM，prefix caching 关闭。
- 官方 vLLM，prefix caching 开启。
- 只加入生命周期统计，不改变策略。
- 生命周期感知驱逐策略。
- 若实现条件允许，加入共享后分叉或 chunk 级复用增强。

这样可以区分“前缀共享本身收益”和“生命周期协同策略增益”。

### 10.3 指标

建议指标包括：

- **Prefix token hit ratio**：复用 prompt token 数 / 可复用 prompt token 总数。
- **Block reuse ratio**：命中已有 full block 数 / 本次请求需要的 full block 数。
- **TTFT**：平均、p50、p95。
- **End-to-end latency**：平均、p50、p95。
- **Throughput**：requests/s、tokens/s。
- **GPU memory footprint**：峰值和平均显存。
- **Eviction frequency**：单位时间驱逐次数。
- **Eviction regret**：窗口内被驱逐后又重建的 block 数 / 被驱逐 block 总数。
- **Recompute ratio**：因未命中或错误驱逐重新 prefill 的 token 数 / 总 prefill token 数。
- **Effective block utilization**：有效 token 容量 / 已分配 block 总容量。
- **Management overhead**：新增元数据和二阶段评分带来的调度开销。

### 10.4 消融实验

为解释策略收益来源，可设计：

1. 去掉共享度因子，只保留热度和 LRU。
2. 去掉重算代价因子，观察长前缀重建开销。
3. 去掉前缀位置因子，观察前段公共 block 是否被误淘汰。
4. 只做 instrumentation 不改策略，验证观测层本身开销。
5. 调整 `w1...w5` 权重，观察不同场景下的策略敏感性。

## 11. 风险与控制

| 风险 | 表现 | 控制方式 |
| --- | --- | --- |
| vLLM 源码复杂 | 修改核心路径容易影响全局 | 先读清 scheduler/cache manager/block pool，先观测再改策略 |
| 显存有限 | 8GB 环境难以跑大模型长上下文 | 使用小模型做机制验证，关键实验迁移到更大显存机器 |
| CoW 实现复杂 | 涉及 block copy、只读语义、分叉映射 | 首版先做共享后分叉统计和驱逐优化，CoW 作为高级阶段 |
| 性能收益不稳定 | 不同 workload 结果差异大 | 用固定矩阵测试，报告适用场景和无收益场景 |
| 策略开销过高 | Python 元数据和排序影响热路径 | side table、候选子集评分、低水位触发、可关闭开关 |
| 过度绑定 vLLM | 长期不可移植 | 把策略描述为生命周期抽象，保留未来 C++ runtime 边界 |

## 12. 阶段性成功标准

为了避免把项目成败绑定到一次性完成所有高级机制，建议分层定义成功：

1. **基础成功**：完成 vLLM 基线复现、源码路径梳理、生命周期事件统计，输出 prefix hit、eviction、rebuild 的可复现实验数据。
2. **中级成功**：实现生命周期感知驱逐，在至少一种共享前缀负载上降低重算比例或稳定 TTFT。
3. **完整成功**：实现共享后分叉的结构化管理，在局部分叉或逐步分叉负载上优于默认机制。
4. **拓展成功**：探索 chunk 级复用或 CoW copy 路径，并明确其工程边界和 C++/CUDA 下沉条件。

## 13. 结论

KV Cache 已经从一个简单缓存技巧演变为 LLM 推理服务中的核心系统资源。它既影响 decode 阶段计算效率，也决定长上下文和高并发服务下的显存上限。现有研究在 token 保留、压缩、分页分配、前缀共享和评测体系上已经提供了重要基础，但仍存在局部优化多、生命周期协同不足、分叉前缀复用有限、驱逐策略过于简单等问题。

KVFabric 的研究价值在于把 KV block 视为完整生命周期对象，统一管理分配、复用、分叉、驱逐和重建。短期以 vLLM 为主平台，在 Python 控制面完成生命周期统计、共享感知驱逐和共享后分叉原型，是当前仓库最可行、风险最可控的路径。长期则应把稳定策略抽象为以 C++ 为核心的可移植 scheduler/runtime，使 KVFabric 不止是一个 vLLM patch，而是面向多后端 LLM serving 的独立缓存调度系统。

## 参考资料

1. Vaswani et al. Attention Is All You Need. NeurIPS 2017.
2. Kwon et al. Efficient Memory Management for Large Language Model Serving with PagedAttention. SOSP 2023.
3. vLLM Project. PagedAttention and Automatic Prefix Caching design materials.
4. Prabhu et al. vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention. 2024.
5. Zhang et al. H2O: Heavy-Hitter Oracle for Efficient Generative Inference of Large Language Models. 2023.
6. Liu et al. KVzip: Adaptive KV-Cache Compression. 2024.
7. Ge et al. Model Tells You What to Discard: Adaptive KV Cache Eviction for LLMs. 2023.
8. Pan et al. AsymKV: Distinguishing the Role of Key and Value Caches for Efficient LLM Inference. 2024.
9. [vLLM 与 llama.cpp 适用性调研](vllm-vs-llamacpp.md)。
10. [KVFabric 可行性报告](../../reports/feasibility_report.md)。
11. [KVFabric 架构说明](../../architecture/overview.md)。
12. [vLLM Baseline Workspace](../../../vllm_baseline/README.md)。
