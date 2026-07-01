# KVFabric 接手后迭代过程：实验问题驱动的代码与架构修改

本文按接手后的真实开发脉络整理 KVFabric 的迭代过程。这里不强行划成 8 次，而是按“相对较大的代码或架构修改”自然分组。每一组都回答四个问题：

1. 是什么实验或长测现象暴露了问题；
2. 问题的根因是什么；
3. 因此改了哪些代码、脚本或架构；
4. 改完以后怎么验证，形成了什么结论。

前期开发 PPT 中已经覆盖的 baseline、指标采集、纯 Python 最小闭环、真实 vLLM 接入、shared-aware、family-protect、早期 admission control 等内容，本文只作为接手基础，不重复展开。本文重点从远程 2 x RTX 3090 长测、hint-aware 改造、真实化 trace、scheduler/admission/controller 重构、Qwen3.5-9B final matrix 这些接手后的工作讲起。

## 接手基础

接手时，KVFabric 已经具备以下基础能力：

- 在 vLLM 0.22.1 的 Python 控制面中接入 lifecycle side table。
- 能记录 `block_allocated`、`block_sealed`、`block_touched`、`block_evicted`、`prefix_lookup` 等 JSONL 事件。
- 已有 shared-aware eviction、family-protect eviction、request-aware / length-aware admission 的早期版本。
- 已有本地 qwen3.5-2B smoke test、模板 family revisit、普通无共享非回归等短实验。
- 已能证明：在模板化 prompt、相似多轮、长期 family 回访场景中，KVFabric 可以减少 rebuilt-from-eviction，提高 prefix-hit tokens；普通无共享场景基本不退化。

接手后的问题不再是“策略有没有雏形”，而是：

> 如何把这个 prototype 推到远程大模型、长周期真实请求、复杂流量、可复现 summary 和最终汇报级实验闭环。

## 改动一：远程长测闭环与验收矩阵基础设施

### 触发问题

本地短实验能说明机制可行，但无法支撑最终系统项目汇报。迁移到远程 2 x RTX 3090 后，首先暴露的是实验工程问题：

- 远程 vLLM overlay 部署容易漏文件。
- 模型启动、环境变量、loadgen、Prometheus 抓取和结果同步依赖手工命令。
- 长测中途失败后，目录里可能只留下部分 rolling 文件，难以判断 run 是否完整。
- 多个 policy 的结果、lifecycle、metrics、raw samples 分散，人工汇总容易出错。
- 没有统一验收矩阵，就会出现很多短测结果互相干扰，最终 PPT 不知道该引用哪组。

### 根因分析

KVFabric 已经有控制面策略，但缺少围绕远程实验的运行基础设施。系统项目的“可运行原型”不只是核心代码，还包括可复现的部署、启动、同步、汇总和验收流程。

### 代码与架构修改

这一阶段围绕 `experiments/long_pressure_benchmark` 建立长测工具链：

- 增加远程部署和运行脚本，统一把 overlay、configs、scripts 同步到远程环境。
- 增加长测 runner，按 policy 顺序启动 vLLM server、等待 ready、运行 loadgen、抓取 Prometheus、保存 env。
- 增加 12h acceptance 设计，把实验从零散短测收敛为可验收模块。
- 设计 saturation / enterprise / sticky conversation 三类长测场景，明确 warmup、low guard、high main、red burst 等阶段。
- 增加结果同步和 summary 生成路径，使远程 run root 能被本地统一分析。
- 设计 fixed-seed、固定请求池、class drift 检查，避免不同 policy 实际跑到完全不同请求分布。

相关文件和文档：

- `docs/current/kvfabric_12h_acceptance_experiment_design.md`
- `docs/current/kvfabric_realistic_long_benchmark_design.md`
- `experiments/long_pressure_benchmark/scripts/deploy_remote_27b_long_benchmark.sh`
- `experiments/long_pressure_benchmark/scripts/sync_remote_27b_benchmark_results.sh`
- `experiments/long_pressure_benchmark/scripts/analyze_acceptance_run.py`

### 验证与影响

后续 27B/9B 的多小时实验都建立在这一套远程闭环上。它解决了“能不能可靠跑完并复现”的问题，为后续所有策略改动提供了统一实验底座。

汇报口径：

> 接手后的第一类大改动，是把 KVFabric 从本地短测推进到远程长测工程：自动部署、自动运行、自动同步、自动 summary，让后续实验可以复现和比较。

## 改动二：Hint-Aware 请求元数据通道

### 触发问题

远程压力实验显示，KVFabric 能减少错误驱逐和 rebuild，但吞吐提升没有达到理想目标。日志分析发现一个关键瓶颈：

- 服务器只能在 prefix lookup 之后知道本地 cache hit 情况。
- 在请求进入 waiting queue 和 admission 决策时，系统并不知道这个请求是 durable hot family、transient family、cold RAG，还是 burst cold traffic。
- 调度和 admission 只能被动根据长度、命中、free pressure 推测请求价值。
- benchmark generator 其实已经知道 request class、tenant、family、phase、expected reuse，但这些信息没有稳定进入 vLLM。

### 根因分析

只靠 block hash lineage 是不够的。block hash index 回答的是“这个 cached block 属于哪个 prefix tree”，但调度和 admission 更早需要知道“这个请求从业务语义上属于哪个 family，未来复用可能性如何”。

因此需要一个显式 request hint channel，把应用侧/网关侧本来就知道的元数据传进 vLLM 控制面。

### 代码与架构修改

这一阶段增加 hint-aware 架构：

- 新增 `KVFabricRequestHints`，解析和归一化 HTTP headers。
- 新增 `HintFamilyIndex` / hint family runtime，用 workload-visible family id 维护运行时统计。
- 扩展 `RequestMeta`，记录 request class、tenant、family、cache priority、expected reuse、phase、burst 等字段。
- OpenAI serving 层从请求 headers 中提取 `x-kvfabric-*` hints，即使普通 tracing 未开启也能传入 `Request.trace_headers`。
- lifecycle 事件统一带 hint 字段，方便按 request id 关联 lookup、schedule、defer、admission、finish。
- admission 和 scheduler 开始读取 hints：
  - durable/high priority 不轻易 defer；
  - low/no-reuse cold requests 在压力下更容易被限制缓存；
  - bypass burst cold requests 可以几乎不进入 prefix cache；
  - transient family 获得少量 discovery budget，而不是完整缓存。

典型 headers：

- `x-kvfabric-request-class`
- `x-kvfabric-tenant-id`
- `x-kvfabric-family-id`
- `x-kvfabric-cache-priority`
- `x-kvfabric-expected-reuse`
- `x-kvfabric-phase`
- `x-kvfabric-burst`

相关文件：

- `vllm/v1/core/kvfabric_hints.py`
- `vllm/v1/core/kvfabric_lifecycle.py`
- `vllm/entrypoints/openai/engine/serving.py`
- `experiments/long_pressure_benchmark/examples/online_trace_loadgen.py`
- `docs/current/kvfabric_hint_aware_scheduler_refactor_design.md`
- `docs/current/kvfabric_hint_refactor_validation_2026-06-22.md`

### 验证与影响

后续 summary 可以输出：

- hint coverage；
- priorities 分布；
- expected reuse 分布；
- admission reasons；
- defer reasons；
- top hint families。

这使 KVFabric 从“只观察 block”扩展为“理解请求意图 + 管理 block 生命周期”的控制面系统。

汇报口径：

> 第二类大改动是把请求语义接入 vLLM：KVFabric 不再只等 prefix lookup 之后被动判断，而是在 admission 和 scheduler 阶段就能看到 request class、family、priority 和 expected reuse。

## 改动三：真实化 Trace Generator 与 Open-Loop Loadgen

### 触发问题

早期 pressure workload 主要验证策略机制，但不够像真实 LLM 服务：

- hot/cold 边界太人工，容易被质疑“只为 KVFabric 设计”。
- 缺少多租户、RAG、agent、长文档、多轮会话等自然复用结构。
- 缺少 open-loop 到达过程，固定并发 closed-loop 会让更快策略跑到请求池后面，造成 workload drift。
- 缺少 hint quality 维度，不能只依赖 perfect hints。

### 根因分析

KVFabric 的目标场景是存在稳定 prefix reuse 的真实 serving 场景，例如企业 RAG、agent loop、多轮对话、长文档 follow-up、租户工作流。workload 需要显式模拟这些结构，否则无法证明策略适用边界。

### 代码与架构修改

这一阶段重构 trace 生成和 trace replay：

- 新增 `generate_realistic_trace.py`，按 profile 生成 `trace.jsonl` 和 prompt 文件。
- 引入 tenant、client、family、session、turn、phase、burst 等字段。
- 支持多种 trace profiles：
  - `general_gateway`
  - `enterprise_mixed`
  - `conversation_sticky`
  - `daily_dedicated_reuse`
  - `sticky_burst`
  - `low_reuse_low_frequency`
- 支持 session reuse：同一 session 的后续 turn 携带之前的 messages，形成真实多轮 prefix。
- 支持 hint regimes：
  - `no_hints`
  - `partial_hints`
  - `full_hints`
  - `noisy_hints`
- 新增 open-loop trace loadgen：
  - 按 `scheduled_at_seconds` 发请求；
  - 用 semaphore 控制 max in-flight；
  - 记录 send delay；
  - 输出 rolling metrics、class metrics、raw samples。

相关文件：

- `experiments/long_pressure_benchmark/examples/generate_realistic_trace.py`
- `experiments/long_pressure_benchmark/examples/online_trace_loadgen.py`
- `docs/current/kvfabric_realistic_long_benchmark_design.md`

### 验证与影响

后续 enterprise normal、interactive latency、low reuse 等实验都来自这套 trace generator。它让实验从“合成 hot/cold 压力”扩展到“多租户、多 family、多 session 的真实化流量”。

汇报口径：

> 第三类大改动是 workload 架构升级：用 trace generator 模拟企业网关、RAG、agent、多轮会话和低复用流量，让 KVFabric 的收益和边界都能被验证。

## 改动四：指标体系重构，加入 e2e、class、segment、SLO Probe

### 触发问题

长测结果开始变多后，发现原有 summary 不能解释复杂现象：

- raw total tok/s 有时只提升 1%-2%，但 SLO goodput 提升很大。
- 某些 class 变快，某些 class 变慢，整体平均值掩盖差异。
- trace 模式下 response latency 不包含排队和发送延迟，无法评价用户端真实等待。
- duration 模式下不同阶段压力不同，必须区分 warmup、high_main、red_burst、revisit。
- SLO 阈值选择会影响 goodput，反复重跑成本高。

### 根因分析

KVFabric 的优化链路是资源管理链路，不一定直接表现为 raw token/s 大幅增长。更合理的指标是：

- SLO 内完成的有效 token；
- e2e latency；
- class-level latency/goodput；
- segment-level goodput；
- prefix hit、warm-family hit、rebuilt-from-eviction 等 lifecycle evidence。

### 代码与架构修改

这一阶段对 loadgen 和 summary 做系统性扩展：

- `online_trace_loadgen.py` 增加：
  - `e2e_latency = send_delay + service latency`
  - e2e p50/p95/p99
  - e2e goodput
  - class-level e2e latency/goodput
  - rolling class metrics
- `online_duration_loadgen.py` 增加：
  - `class_slo_seconds`
  - `slo_probe_seconds`
  - `slo_probe_metrics`
  - `slo_probe_class_stats`
  - `slo_probe_segment_stats`
  - `class_segment_metrics.json`
- summary 逻辑改为展示：
  - overall throughput/latency；
  - lifecycle；
  - admission and scheduler；
  - hint-aware behavior；
  - request class metrics；
  - segment metrics；
  - selected SLO probe。
- acceptance analysis 动态发现 policies 和 segments，避免写死旧实验。

相关文件：

- `experiments/long_pressure_benchmark/examples/online_trace_loadgen.py`
- `experiments/long_pressure_benchmark/examples/online_duration_loadgen.py`
- `experiments/long_pressure_benchmark/scripts/analyze_acceptance_run.py`
- `docs/current/kvfabric_throughput_optimization_design_2026-06-26.md`

### 验证与影响

这次改动后来直接支撑了 final matrix 解释：

- prefill throughput 能展示 selected SLO goodput、segment goodput、rebuilt 下降。
- interactive latency 能展示前台 class 全部改善，同时后台 class 退化。
- low reuse 能说明没有 prefix hit，但 admission 降低 evictions 和 queue backlog。

汇报口径：

> 第四类大改动是观测体系升级：从单一 tok/s 变成 e2e、class、segment、SLO 和 lifecycle 联合解释，避免只看平均值误判策略。

## 改动五：Hit-Aware Positive Scheduler 与 Queue Affinity

### 触发问题

长测复盘发现，shared-aware/family-protect 已经能显著减少 rebuilt-from-eviction，但 prefix hit ratio 仍不够高，吞吐提升距离目标还有差距：

- 策略能保护 cache 中的高价值 block；
- 但等待队列中哪些请求先进入 batch，仍主要按 FCFS；
- 如果高复用请求排在后面，cache 保护收益不能及时转化为命中；
- 早期 scheduler 只有负向 deferral，缺少正向把可能命中的请求提前的能力。

### 根因分析

只做 eviction 是“保护资源”，但还需要 scheduler affinity 让更可能命中 prefix cache 的请求更早使用这些资源。否则 cache 里有热 prefix，队列却先跑大量冷 miss，请求级收益会被稀释。

### 代码与架构修改

这一阶段引入 positive scheduler：

- Scheduler 在 waiting queue 中扫描一个有限窗口。
- 根据 hints、family runtime、request class、prompt length、expected reuse 等给候选请求打分。
- 增加 `peek_computed_tokens()`，在不分配 block、不写 lifecycle 事件的前提下估计当前请求的 prefix hit tokens。
- 对 hint 预选出的 top-K 候选做实际 prefix hit 校验，避免只凭 hint 误判。
- 增加参数控制：
  - positive scan window；
  - positive max per step；
  - positive score margin；
  - hit-aware top-K；
  - hit-aware min tokens。
- 记录 `request_promoted` 事件，包括 promote score、hit tokens 等。

相关文件：

- `vllm/v1/core/kv_cache_manager.py`
- `vllm/v1/core/sched/scheduler.py`
- `vllm/v1/core/kvfabric_lifecycle.py`
- `docs/current/kvfabric_throughput_optimization_design_2026-06-26.md`
- `docs/current/kvfabric_30pct_throughput_refactor_research.md`

### 验证与影响

这条线让 KVFabric 不再只是 eviction/admission，而开始影响 waiting queue。后续 unified controller 中的 `scheduler_strength` 就来自这里。

不过实验也暴露了风险：promotion 过强会破坏 FCFS 公平性和尾延迟。因此后面又加入 sticky fairness 和 latency guard。

汇报口径：

> 第五类大改动是从“只管 cache block”扩展到“cache-aware scheduler”：保护了热 prefix 以后，还要让可能命中的请求更早进入 batch。

## 改动六：Sticky Conversation Fairness 与 Latency Guard

### 触发问题

Sticky conversation 长测后，发现复用优先调度有副作用：

- 长对话/agent follow-up 有局部延迟改善。
- 但 `decode_heavy_noise` 这类长输出、低复用请求尾延迟明显变差。
- scheduler promotion 如果持续让高复用请求插队，低复用长输出可能被长期压在队列中。
- 这说明只证明 cache 命中保护还不够，必须处理公平性和尾延迟。

### 根因分析

真实 serving 不只有高复用请求。后台 decode-heavy、低复用 cold lookup 虽然优先级低，也不能无限等待。scheduler 需要有 age guard 和 promotion/defer budget，保证 foreground priority 不变成 starvation。

### 代码与架构修改

这一阶段增加 fairness/latency guard：

- 增加 latency-protected classes。
- 增加 head age guard：
  - 如果队头低复用/长输出请求等待超过阈值，后面的高复用请求不能继续插队。
- 增加 latency promotion：
  - 某些受保护类等待超过阈值后，可以被提升。
- 增加 defer cap：
  - 每个调度 step 最多 defer 几个请求；
  - 每个 request 最多 defer 几次；
  - low-reuse 请求有单独 max age cap。
- 在 lifecycle metrics 和 summary 中新增：
  - `request_latency_promoted`
  - latency promotes；
  - defer skips；
  - promotion skips。

相关文件：

- `vllm/v1/core/sched/scheduler.py`
- `vllm/v1/core/kvfabric_lifecycle.py`
- `docs/current/kvfabric_sticky_conversation_fairness_refactor_2026-06-26.md`
- `docs/current/kvfabric_sticky_latency_protected_scheduler_2026-06-27.md`
- `docs/current/kvfabric_sticky_latency_throughput_refactor_2026-06-27.md`

### 验证与影响

这一阶段没有简单得到“所有请求都更快”的结论，但明确了 scheduler 的系统边界：

- promotion 必须有保护范围；
- low-reuse/decode-heavy 不能无限让路；
- latency 结论必须按 class 解释，而不是只看整体平均。

汇报口径：

> 第六类大改动是 scheduler fairness：从单纯偏向复用请求，升级为有 age guard、defer cap 和 latency-protected class 的有界调度。

## 改动七：Dashboard / Replay / Run State，可视化和失败可诊断

### 触发问题

长测过程中出现过 run 不完整的问题：远程 job log 停在 server ready 附近，目录里只有 LRU 的早期 rolling 文件，没有 final metrics，也没有后续 policy 结果。如果只看目录存在，很容易误以为实验完成。

同时，最终汇报如果只放表格，很难直观看出 KV block 生命周期和 rebuilt-from-eviction。

### 根因分析

长测系统需要能区分：

- running；
- completed；
- failed；
- partial；
- stalled。

而 replay/dashboard 需要稳定读取 lifecycle JSONL、rolling metrics、raw output samples 和 Prometheus samples。否则可视化会把坏数据当成正常数据。

### 代码与架构修改

这一阶段设计并部分实现实时实验面板和 replay：

- 新增 dashboard / replay 入口设计：
  - `run_kvfabric_dashboard.py`
  - `build_replay.py`
  - `render_replay_gif.py`
- 长测 runner 新增状态文件：
  - `run_state.json`
  - `policy_state.json`
  - `heartbeat.json`
- loadgen 增加 `x-kvfabric-trace-request-id`，生命周期事件可以和 trace/raw sample 对齐。
- `KVFabricRequestHints` 增加 `trace_request_id`。
- 增加 `rolling_class_metrics.jsonl`，实时记录 class-level completed、tok/s、goodput、latency、SLO miss。
- runner 显式捕获 vLLM server 和 loadgen 退出码，失败后不再继续进入 metrics 阶段伪装正常运行。
- dashboard parser 需要按行容错处理 JSONL，坏行计数但不中断。

相关文件和文档：

- `docs/current/kvfabric_dashboard_replay_design_2026-06-28.md`
- `experiments/long_pressure_benchmark/examples/online_trace_loadgen.py`
- `vllm/v1/core/kvfabric_hints.py`
- `vllm/v1/core/kvfabric_lifecycle.py`

### 验证与影响

这类改动提升的是实验可靠性和展示能力。它让最终汇报可以从“数字结果”扩展到“KV block 生命周期 replay”，并且避免把 partial/stalled run 当成完整结果。

汇报口径：

> 第七类大改动是可视化和实验状态管理：长测不仅要跑，还要能判断是否真的跑完，并能用 replay 展示 KV cache 生命周期变化。

## 改动八：Unified Controller，把策略从离散 policy 改成参数向量

### 触发问题

随着 admission、eviction、scheduler、SLO protection 都加入后，旧的策略名开始变得混乱：

- `shared_aware`、`family_protect`、`kvfabric_latency` 等名字无法精确说明打开了哪些机制。
- 不同实验需要不同组合，例如 throughput 要强 admission、轻 eviction、关 scheduler；latency 要关 admission/eviction、开 scheduler。
- 如果通过脚本散落环境变量控制，参数容易泄漏到下一阶段。
- 9B 上强 re-ranking 或强 scheduler 可能负优化，需要连续强度而不是开/关。

### 根因分析

KVFabric 已经从单一 eviction policy 演化为一个 controller。它应该用统一参数向量表达各控制面的干预强度，而不是靠策略名硬编码行为。

### 代码与架构修改

这一阶段引入 `KVFabricControlConfig`：

- `admission_strength`
- `eviction_strength`
- `scheduler_strength`
- `slo_protection_strength`
- `hint_trust`
- `low_reuse_cache_fraction`
- `transient_cache_fraction`
- `bypass_cache_fraction`
- `durable_cache_fraction`
- `cold_cache_fraction`

同时保留 profile 作为 preset：

- `off` / `lru`
- `admission_dominant`
- `throughput`
- `throughput_protect`
- `latency_protected`
- `rebuilt`

算法层改动：

- Admission 改成连续 fraction，而不是固定截断。
- Eviction 介入强度连续化，低强度只保护明显高价值 block。
- Scheduler 介入强度连续化，`scheduler_strength=0` 时完全不改调度。
- lifecycle metrics 写入 controller 字段，使 summary 能展示当前参数。
- runner 使用 stage-local subshell env，避免 throughput profile 泄漏到 latency 或 guard stage。

相关文件：

- `vllm/v1/core/kvfabric_lifecycle.py`
- `experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh`
- `experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh`
- `docs/current/kvfabric_unified_controller_9b_matrix_2026-06-29.md`

### 验证与影响

最终 summary 中可以直接展示每个 policy 的 Admission / Eviction / Scheduler / SLO protect 参数，使实验解释更清楚。

汇报口径：

> 第八类大改动是统一 controller：KVFabric 不再是几个离散策略名，而是 Admission、Eviction、Schedule、SLO protection 的连续控制向量。

## 改动九：Qwen3.5-9B 中等容量实验框架

### 触发问题

27B 或 2B 的结果不能直接作为最终主结果。迁移到 Qwen3.5-9B 后，旧参数不稳定：

- 27B 的压力和 SLO 不能直接平移到 9B。
- 9B 在 2 x RTX 3090 上的 prefill/decode 和 KV 容量平衡不同。
- 如果只用极小 KV cache，容易被质疑是极端场景。
- 如果容量太大，又很难制造有意义的 cache competition。

### 根因分析

模型规模、GPU 显存、并发、KV block 数、SLO 都会改变策略收益。最终实验需要把容量作为显式变量，并选择一个中等容量作为主证明口径。

### 代码与架构修改

这一阶段新增 9B 实验框架：

- 新增 profile：
  - `vllm_baseline/profiles/qwen3_5_9b.env`
  - `MODEL_ID=Qwen/Qwen3.5-9B`
  - `TENSOR_PARALLEL_SIZE=2`
  - `MAX_MODEL_LEN=4096`
  - `GPU_MEMORY_UTILIZATION=0.70`
  - `MAX_NUM_SEQS=64`
  - `MAX_NUM_BATCHED_TOKENS=24576`
- 定义容量档：
  - small：0.55
  - medium：0.70
  - large：0.85
- 新增 9B configs：
  - capacity sweep
  - daily dedicated reuse
  - sticky burst
  - enterprise normal
  - low reuse
  - saturation reuse proof
  - rebuilt pressure
  - working set gap
  - foreground latency background
- 新增 9B quick loop 和 12h matrix runner。

相关文件：

- `vllm_baseline/profiles/qwen3_5_9b.env`
- `experiments/long_pressure_benchmark/configs/qwen3_5_9b_*.json`
- `experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_quick_loop.sh`
- `experiments/long_pressure_benchmark/scripts/run_qwen3_5_9b_12h_matrix.sh`
- `docs/current/kvfabric_medium_capacity_generalization_design_2026-06-29.md`

### 验证与影响

这次改动把最终口径从“极端 KV cache 紧张”改为“中等容量下的高压服务场景”。它更适合期末汇报，也更容易解释策略边界。

汇报口径：

> 第九类大改动是把实验目标迁移到 Qwen3.5-9B，并显式引入 small/medium/large 容量；最终主结论以 medium capacity 为核心。

## 改动十：Admission 路径重构与 double-limit 修复

### 触发问题

9B high-pressure 实验中发现，只靠 eviction 不足以解决 cold traffic pollution：

- cold RAG unique 和 burst cold 会持续写入 prefix cache。
- 即使 eviction 最后会优先驱逐冷块，冷块进入 cache 的过程已经造成 churn。
- admission 如果太弱，cache 被低价值请求污染。
- admission 如果太强，又会伤害 durable family warmup。
- 代码审计还发现 admission limit 不能在多个层级重复应用，否则上层记录的 cached blocks 数量和底层实际 hash 状态可能不一致。

### 根因分析

Admission 是入口控制，必须在写入 prefix cache 前做；但它的位置必须唯一。vLLM 的 `SingleTypeKVCacheManager.cache_blocks()` 和 `BlockPool.cache_full_blocks()` 对 `num_full_blocks` 有一致性假设，重复 limit 会破坏这个假设。

### 代码与架构修改

策略层：

- `limit_cache_blocks()` 读取：
  - prompt tokens；
  - prefix hit tokens；
  - request class；
  - cache priority；
  - expected reuse；
  - free pressure；
  - eviction risk；
  - durable/low/transient/bypass/cold fraction。
- 对 low/no-reuse/bypass/transient 请求按压力限制 full blocks。
- 对 durable/high/session/family 复用请求保留完整缓存机会。
- 输出 `cache_admission_limited` 事件，记录 reason、saved blocks、risk、limited classes。

代码位置：

- admission limit 只在 `SingleTypeKVCacheManager.cache_blocks()` 应用。
- `BlockPool.cache_full_blocks()` 只负责对传入范围内的 full blocks 写 hash 和发 sealed event，不再重复截断。
- 保留 double-limit fix，避免触发 `assert block.block_hash is not None` 这类状态不一致。

相关文件：

- `vllm/v1/core/kvfabric_lifecycle.py`
- `vllm/v1/core/single_type_kv_cache_manager.py`
- `vllm/v1/core/block_pool.py`
- `docs/current/kvfabric_active_experiment_memory.md`
- `docs/current/kvfabric_9b_final_matrix_and_latency_iteration_2026-06-30.md`

### 验证与影响

在 final throughput stage 中，KVFabric 的 admission 主要限制 cold/burst 请求：

- admission limited：26,115 次；
- saved blocks：68,475；
- rebuilt-from-eviction：11,790 -> 1,725；
- prefix hit ratio：21.28% -> 30.93%；
- warm-family hit：41.41% -> 71.11%。

在 low-reuse stage 中，prefix hit 为 0，但 admission saved 2,293 blocks，evictions 从 4,348 降到 777，说明 admission 对低复用场景也能减少 cache churn。

汇报口径：

> 第十类大改动是 admission 路径重构：不是所有 full blocks 都值得进 prefix cache；低价值请求在入口处被限制，同时保证 limit 只发生一次，维护 vLLM block hash 一致性。

## 改动十一：Latency Header Plumbing 与 Scheduler 重评分

### 触发问题

9B latency quick runs 一开始几乎没有效果：

- `kvfabric_latency` 和 LRU 接近。
- scheduler promotion counters 为 0 或很低。
- 事件中 `hint_slo_ms=0`，session/turn 也经常为空。
- 修复部分参数后，promotion 生效，但 p95 反而变差。
- queue pressure 不足时 scheduler 没有发挥空间；queue pressure 足够时，又容易把 background/decode 也错误 promotion。

### 根因分析

这个问题分三层：

1. hint 没有完整穿过 OpenAI serving / tracing header whitelist；
2. 旧 latency workload 没有足够 waiting queue 竞争；
3. 旧 promotion 算法过粗，只看局部候选或过宽 SLO，容易提升错误请求。

### 代码与架构修改

Header plumbing：

- `vllm/tracing/utils.py` 增加 whitelist：
  - `x-kvfabric-slo-ms`
  - `x-kvfabric-session-id`
  - `x-kvfabric-turn-index`
  - `x-kvfabric-hint-confidence`
- `online_trace_loadgen.py` 在 partial hints 下也发送 session/turn。
- OpenAI serving 在 tracing disabled 时也保留 KVFabric hint headers。

Queue pressure：

- 新增 latency queue configs：
  - `qwen3_5_9b_interactive_latency_queue_quick_10m.json`
  - `qwen3_5_9b_interactive_latency_queue_45m.json`
- latency profile 降低 server admitted seqs、提高 loadgen max in-flight，使 waiting queue 真正形成竞争。

Scheduler scoring：

- 增加 `KVFABRIC_SCHEDULER_LATENCY_SCAN_WINDOW`。
- 增加 `KVFABRIC_SCHEDULER_LATENCY_MAX_PER_STEP`。
- latency promotion 从“第一个 aged candidate”改成“扫描候选并选择最高分”。
- 分数考虑：
  - request age；
  - durable/session hints；
  - prefix reuse value；
  - family hit evidence；
  - cold/decode/low-reuse/bypass penalty。
- 增加 promotion/defer/skip 事件，便于复盘。

相关文件：

- `vllm/tracing/utils.py`
- `vllm/entrypoints/openai/engine/serving.py`
- `vllm/v1/core/sched/scheduler.py`
- `vllm/v1/core/kvfabric_lifecycle.py`
- `experiments/long_pressure_benchmark/examples/online_trace_loadgen.py`
- `docs/current/kvfabric_active_experiment_memory.md`
- `docs/current/kvfabric_9b_final_matrix_and_latency_iteration_2026-06-30.md`

### 验证与影响

最终 latency stage 中：

- latency promotions：0 -> 3,442；
- overall e2e p95：273.888s -> 221.542s；
- 6 个前台 foreground classes 的 e2e p95 均改善 30% 以上；
- background classes 出现明确退化。

因此最终口径收敛为 foreground-priority latency protection，并明确收益集中在有复用和 SLO 压力的请求类别上。

汇报口径：

> 第十一类大改动是 latency 调度链路修复：先让 SLO/session/turn 真正进入 vLLM，再制造真实队列压力，最后把 promotion 改成带 class 和 hint 惩罚的有界评分。

## 改动十二：Background Injection 与 Guard 场景，修正 Trace 混合比例失真

### 触发问题

latency tuned8 暴露了 trace generator 的一个隐藏问题：

- 配置里 background/decode class weights 加起来约 16%；
- 但最终 trace 中 background/decode 只有约 5.3%；
- 因为 session reuse 会放大 session classes，`class_weights` 控制的是新请求/新 session 起点，不等于最终请求占比；
- 这样 foreground/background 混部实验不够真实。

同时，最终汇报还需要证明 KVFabric 在普通企业混合和低复用场景中的边界，而不是只展示最有利的高压/前台场景。

### 根因分析

trace generator 的权重语义会受到 session reuse 的二次放大。要稳定构造后台流量，不能只靠 class weights，而应独立注入 background 请求。

此外，guard 场景用于说明策略边界和非回归风险，收益规模本身不是该场景的核心目标。

### 代码与架构修改

Trace generator：

- `generate_realistic_trace.py` 新增：
  - `background_mix_probability`
  - `background_class_weights`
- background 请求按独立概率插入，不再被 session reuse 稀释。
- 新增 foreground/background latency configs：
  - `qwen3_5_9b_foreground_latency_background_quick_8m.json`
  - `qwen3_5_9b_foreground_latency_background_45m.json`
  - `qwen3_5_9b_foreground_latency_background_90m.json`

Guard configs：

- `qwen3_5_9b_enterprise_normal_75m.json`
- `qwen3_5_9b_low_reuse_45m.json`

Final matrix：

- 保留四类角色：
  - high-pressure prefix throughput；
  - foreground-priority latency；
  - enterprise normal guard；
  - low-reuse guard。
- summary 中明确区分：
  - prefix reuse win；
  - admission/backlog/churn win；
  - foreground latency win；
  - no-reuse non-regression / low-value admission win。

相关文件：

- `experiments/long_pressure_benchmark/examples/generate_realistic_trace.py`
- `experiments/long_pressure_benchmark/configs/qwen3_5_9b_foreground_latency_background_*.json`
- `experiments/long_pressure_benchmark/configs/qwen3_5_9b_enterprise_normal_75m.json`
- `experiments/long_pressure_benchmark/configs/qwen3_5_9b_low_reuse_45m.json`
- `experiments/long_pressure_benchmark/final_12h_results/2026-06-30_qwen3_5_9b_final_matrix/analysis/final_12h_sync_and_analysis.md`

### 验证与影响

最终四个 summary 都已生成：

- prefill throughput：selected SLO goodput +97.80%，rebuilt -85.37%。
- interactive latency：overall e2e p95 改善 19.11%，6 个 foreground classes 均改善 30% 以上。
- enterprise normal：goodput +17.37%，e2e p95 改善 64.33%，但 lifecycle 证据显示主要来自 admission 降低 churn/backlog，而不是纯 prefix reuse。
- low reuse：prefix hit 和 rebuilt 均为 0，但 admission saved blocks、evictions 下降，说明收益来自低价值 cache admission 控制。

汇报口径：

> 第十二类大改动是修正 trace 混合比例和补 guard 场景：foreground/background 不能只靠 class_weights，低复用场景也不能被误讲成 prefix reuse 收益。

## 自然演进总览

| 顺序 | 大改动 | 实验暴露的问题 | 核心代码/架构变化 |
| --- | --- | --- | --- |
| 1 | 远程长测闭环 | 手工远程实验不可复现 | deploy/run/sync/summary/acceptance |
| 2 | Hint-aware 请求通道 | admission/scheduler 不知道请求意图 | `KVFabricRequestHints`、hint headers、hint family runtime |
| 3 | 真实化 trace/loadgen | hot/cold workload 不够真实 | tenant/family/session/turn/open-loop trace |
| 4 | 指标体系重构 | raw tok/s 解释不了收益 | e2e、class、segment、SLO probe、selected SLO |
| 5 | Positive scheduler | 只保护 cache，不保证命中请求先跑 | waiting queue scan、peek hit、request promotion |
| 6 | Fairness/latency guard | 复用优先会伤害 decode-heavy | age guard、defer cap、latency-protected classes |
| 7 | Dashboard/replay/state | partial/stalled run 难识别 | run_state、heartbeat、rolling class metrics、replay |
| 8 | Unified controller | policy 名称和参数散落 | continuous Admission/Eviction/Schedule/SLO vector |
| 9 | 9B 中等容量框架 | 27B 参数不能平移 | Qwen3.5-9B profile、capacity profiles、9B configs |
| 10 | Admission 路径重构 | cold traffic 污染 cache，limit 位置有风险 | hint-aware admission、single limit path、double-limit fix |
| 11 | Latency 链路修复 | SLO/session 丢失，promotion 粗糙 | header whitelist、queue pressure、latency scoring |
| 12 | Background injection / guard | class weights 不能保证最终比例 | independent background injection、enterprise/low-reuse guard |

## 最适合 PPT 的讲法

建议不要把这一部分讲成“我们最后跑了哪些实验”，而是讲成“实验不断暴露系统问题，我们不断把问题沉淀成代码和架构改进”：

1. 远程长测暴露可复现问题，所以先建设长测闭环。
2. 长测收益解释不清，所以补 e2e/class/segment/SLO/lifecycle 指标。
3. scheduler/admission 看不到请求语义，所以建立 hint-aware request channel。
4. 旧 workload 不够真实，所以重构 trace generator 和 open-loop loadgen。
5. 只保护 cache 不够，所以加入 positive/hit-aware scheduler。
6. promotion 伤害后台请求，所以加入 fairness、age guard 和 latency guard。
7. 长测 run 可能 partial/stalled，所以加入 run state、heartbeat、dashboard/replay。
8. 策略名越来越乱，所以抽象 unified controller。
9. 迁移 9B 后容量和 SLO 全变，所以建立 9B medium-capacity 实验框架。
10. cold traffic 污染 cache，所以重构 admission，并修正 double-limit 一致性。
11. latency 初期无效，所以修 header plumbing、queue pressure 和 latency scoring。
12. trace 混合比例失真，所以加入 independent background injection 和 guard 场景。

一句话总结：

> 接手后的核心工作，是把前期 KVFabric 策略 prototype 放到远程大模型长测中，用实验不断发现系统问题，再把这些问题落成 hint 通道、真实化 trace、e2e 指标、scheduler、admission、controller、dashboard 和 final matrix 的一系列架构修改。
