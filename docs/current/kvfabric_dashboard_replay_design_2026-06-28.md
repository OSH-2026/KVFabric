# KVFabric 实时实验面板与 KV Cache Replay 设计

日期：2026-06-28

## 目标

现在的长测已经能产出吞吐、延迟、prefix hit、rebuilt-from-eviction、admission、scheduler 等指标，但主要还是 Markdown summary 和 JSON 文件。验收展示时只看表格不够直观，很难一眼看出策略在 KV cache 生命周期上的作用。

这份设计把实验包装成两个可视化入口：

1. 实时实验面板  
   在 robowalker 跑 benchmark 的同时启动一个网页。通过 SSH 端口转发在本地浏览器查看当前策略、进度、吞吐、延迟、cache pressure、prefix hit、输入输出样本、错误状态和日志。

2. KV Cache Replay  
   读取一次实验的 `kvfabric_lifecycle.jsonl` 或采样事件，重建 KV block 状态随时间变化的过程。实时页面中可以低帧率播放，实验结束后可以导出 20 秒左右的 GIF/MP4，用来展示 LRU 与 shared-aware/family-protect 的差异。

参考的 `quant_trade_framework/tools/run_dashboard.py` 是 Streamlit + Plotly 的宽布局面板。KVFabric 这里可以继续用 Streamlit/Plotly，因为部署简单、端口转发方便、对现有 JSON/JSONL 文件友好。视觉上需要更接近系统监控面板：深色背景、策略状态灯、时间轴、热力图、事件流、对比卡片和 replay 动画放在同一页。

## 使用方式

建议新增目录：

```text
experiments/long_pressure_benchmark/dashboard/
  run_kvfabric_dashboard.py
  kvfabric_run_reader.py
  kv_cache_replay.py
  render_replay_gif.py
```

建议新增脚本：

```text
experiments/long_pressure_benchmark/scripts/run_remote_27b_dashboard.sh
experiments/long_pressure_benchmark/scripts/start_remote_27b_sticky_with_dashboard.sh
experiments/long_pressure_benchmark/scripts/export_kv_cache_replay.sh
```

实时查看：

```bash
ssh -L 8501:127.0.0.1:8501 robowalker
```

远程启动：

```bash
cd /home/zhoujiarun/KVFabric
.venv_kvfabric_0221/bin/python -m streamlit run \
  experiments/long_pressure_benchmark/dashboard/run_kvfabric_dashboard.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  -- \
  --run-root experiments/long_pressure_benchmark/runs/<run_dir> \
  --job-log vllm_baseline/runtime_kvfabric_0221/jobs/remote_27b_sticky_conversation_trace_4h.log
```

如果 benchmark 和 dashboard 一起启动，可以让 benchmark launcher 在创建 `run_root` 后写出 `run_state.json`，再启动 dashboard。dashboard 不负责控制实验，只负责读取文件和展示状态。

## 页面结构

页面整体使用深色背景，主色用绿色/青色表示正常，黄色表示压力或等待，红色表示错误或异常退出。布局分为五个区域。

### 1. 顶部总览

顶部是一排状态卡：

- Run name：当前 run 目录名。
- Policy：`lru` / `shared_aware` / `family_protect`。
- Stage：`trace generated` / `server starting` / `loadgen running` / `summarizing` / `completed` / `failed`。
- Elapsed：当前策略已跑多久。
- Progress：完成请求数 / trace 请求数。
- Throughput：total tok/s、goodput tok/s。
- Latency：avg / p95 / p99。
- KV pressure：KV cache usage、waiting/running requests。
- Reuse：prefix hit rate、prefix hit tokens。
- Lifecycle：evicted、rebuilt-from-eviction、admission saved blocks。

这部分要一眼能看出实验是否还活着。如果父进程不在、`metrics.json` 不存在、`rolling_metrics.jsonl` 长时间没有增长，状态卡显示 `stalled`，并给出最后更新时间。

### 2. 策略时间线

三条横向 lane：

```text
lru            [ server ][ loadgen .............. ][ summarize ]
shared_aware   [ pending ]
family_protect [ pending ]
```

每条 lane 用颜色表示状态：

- 灰色：未开始。
- 蓝色：server starting。
- 绿色：loadgen running。
- 黄色：summary pending 或日志停更。
- 红色：failed。

这能解决当前远程实验中容易遇到的问题：job log 只写到了 server ready，父进程已经退出，目录里只有 lru 的早期 rolling 文件。面板需要把这种情况标出来，而不是看起来像正常跑完。

### 3. 性能与请求流

左侧是滚动曲线：

- completed/offered req/s。
- total tok/s 与 goodput tok/s。
- avg/p95/p99 latency。
- SLO miss rate。
- send delay p95。
- KV cache usage。
- num_requests_running / num_requests_waiting。
- prefix cache queries/hits。

右侧是请求流和输入输出：

- 最近完成请求列表：request id、class、tenant、family、turn、latency、tokens、SLO。
- 输入摘要：从 `trace/trace.jsonl` 和 `trace/prompts/<id>.json` 反查。长 prompt 只展示前 1000-2000 字符，并显示总字符数、消息数、class、expected reuse、priority。
- 输出摘要：从 `raw_outputs_sample.jsonl` 读取。输出为空时显示“当前采样未命中”，同时提示 sample rate。
- 错误列表：错误类型、request class、时间、headers。

输入输出不要全量展开，否则页面会很乱。默认显示摘要，点击后展开完整样本。

### 4. KV Cache Replay 预览

页面中间放一个实时 replay 面板，低帧率刷新，比如 1-2 FPS。

推荐两种视图：

1. Block grid  
   每个格子是一个 KV block。颜色表示状态，亮度表示 retain score 或 hit count。适合展示当前缓存形态。

2. Event timeline  
   横轴是时间，纵轴是 block id 或 block group。颜色点表示状态变化。适合看 LRU 下热块被驱逐的过程。

顶部显示当前事件：

- policy
- time offset
- request class
- request id / family id
- cache pressure
- event type

右侧累计计数：

- prefix hit tokens
- prefix hit rate
- evicted blocks
- rebuilt-from-eviction
- admission limited events
- admission saved blocks
- scheduler defers
- scheduler promotions
- latency promotions

### 5. 策略对比与结论

实验完成后页面自动切到比较模式：

- lru / shared_aware / family_protect 的吞吐、goodput、平均延迟、p95、p99。
- prefix hit、rebuilt、evicted、admission saved、scheduler promotes。
- request class 维度的延迟对比，重点看 `decode_heavy_noise`、`deep_multi_turn_chat`、`long_doc_followup_qa`。
- 自动生成一句简短结论，例如：
  - shared-aware 降低了 rebuilt-from-eviction，但 decode-heavy p95 仍高。
  - latency-protected scheduler 触发了 N 次，主要来自 decode-heavy。
  - 如果 total tok/s 没提升但 p95 降低，标注为 Sticky latency win，不拿它证明吞吐。

## 数据源

当前长测已经产生这些文件。

```text
<run_root>/trace/trace.jsonl
<run_root>/trace/trace_summary.json
<run_root>/trace/prompts/*.json
<run_root>/<policy>/online_trace/env.json
<run_root>/<policy>/online_trace/rolling_metrics.jsonl
<run_root>/<policy>/online_trace/prometheus_cache_samples.jsonl
<run_root>/<policy>/online_trace/raw_outputs_sample.jsonl
<run_root>/<policy>/online_trace/metrics.json
<run_root>/<policy>/online_trace/class_metrics.json
<run_root>/<policy>/kvfabric_lifecycle.jsonl
<run_root>/<policy>/kvfabric_lifecycle_metrics.json
<run_root>/<policy>/prometheus_metrics_summary.json
<run_root>/remote_27b_benchmark_summary.md
vllm_baseline/runtime_kvfabric_0221/jobs/<job>.log
```

实时页面优先读取 rolling 文件：

- `rolling_metrics.jsonl`：吞吐、延迟、completed/offered/errors。
- `prometheus_cache_samples.jsonl`：KV usage、running/waiting、prefix hits。
- `kvfabric_lifecycle.jsonl`：block 生命周期、request hint、admission、scheduler、eviction。
- `raw_outputs_sample.jsonl`：输出样本和错误样本。
- `trace.jsonl` + prompts：输入内容和请求元信息。
- job log：当前阶段、server ready、错误栈。

实验结束后读取 final 文件：

- `metrics.json`
- `class_metrics.json`
- `kvfabric_lifecycle_metrics.json`
- `remote_27b_benchmark_summary.md`

## 实时数据读取器

需要实现一个轻量的 `KVFabricRunReader`：

```text
KVFabricRunReader
  discover_run_root()
  discover_current_policy()
  read_job_state()
  tail_rolling_metrics()
  tail_prometheus_samples()
  tail_lifecycle_events()
  tail_raw_outputs()
  load_trace_index()
  load_prompt_excerpt(request_id)
  build_live_snapshot()
```

关键点：

- 用文件 offset 增量读取 JSONL，避免每次刷新读完整大文件。
- 遇到半行 JSON、NUL 字节、截断行时跳过，并在页面显示 parse warning。
- 保存最近 N 条事件到内存，默认 50k 条。
- block 状态用 dict 维护：`block_id -> BlockState`。
- request 状态用 dict 维护：`request_id -> RequestState`。
- 每次刷新只处理新增事件，页面保持 2-5 秒刷新间隔。
- 如果 dashboard 中途打开，需要从头读一遍 lifecycle，或优先读取 checkpoint snapshot。

为了降低实时 replay 开销，建议后续新增 snapshot 文件：

```text
<policy>/kvfabric_block_snapshot.jsonl
```

每 5 秒或每 5000 个事件写一次：

```json
{
  "elapsed_seconds": 123.4,
  "policy": "shared_aware",
  "blocks": [
    {
      "block_id": 17,
      "state": "SHARED",
      "prefix_depth": 3,
      "hit_count": 4,
      "share_degree": 2,
      "retain_score": 31.0,
      "family_id": 12
    }
  ],
  "counters": {
    "prefix_hit_tokens": 8192,
    "rebuilt_from_eviction": 21,
    "admission_saved_blocks": 430
  }
}
```

没有 snapshot 也可以工作，只是大文件打开会慢一些。

## KV Cache Replay 设计

### 状态定义

颜色表：

| State | 含义 | 颜色 |
|---|---|---|
| FREE | 未分配或无 hash | 深灰 |
| ACTIVE | 正在被请求使用 | 蓝色 |
| SEALED | 已写入 prefix cache | 青色 |
| SHARED | 被复用或 ref_count > 1 | 绿色 |
| COOLING_WARM | 已释放但仍在 cache 中 | 黄色 |
| COOLING_HOT | 命中过或共享过，释放后仍有价值 | 橙色 |
| EVICTED | 被驱逐 | 红色 |
| REBUILT | 之前驱逐后又重建 | 紫色闪烁 |

`REBUILT` 不需要长期保存为状态。遇到 `block_sealed` 且 `rebuilt_from_eviction=true` 时，在当前帧闪烁 0.5-1 秒，然后回到 `SEALED` 或 `SHARED`。

亮度映射：

- `hit_count` 越高越亮。
- `share_degree` 越高边框越粗。
- `retain_score` 越高饱和度越高。
- `family_regret_count > 0` 加红色描边。

### 时间轴

`kvfabric_lifecycle.jsonl` 中有 `time_ns`，是 monotonic 时间。单个 policy 内可以用第一条事件作为 `t=0`。如果要和 rolling metrics 对齐，需要新增 `policy_started_wall_time` 或 `policy_started_epoch_seconds`，否则只能显示相对时间。

推荐生成 replay 时统一压缩到固定时长：

- 默认输出 20 秒。
- FPS 20 或 30。
- 真实实验时长 4h/12h 压缩到 20s。
- 每帧处理一段事件，并更新 block grid。
- 对事件过密的区间做聚合，不逐事件画完整帧。

### Grid 视图

对于 27B 当前配置，GPU KV blocks 大约 180-200 个，直接画 grid 很合适：

```text
block 0  block 1  block 2  ... block 15
block 16 block 17 block 18 ... block 31
...
```

如果后续 block 数变大：

- 默认只显示 top active/hot blocks。
- 或按 block_id 分桶，每个格子代表多个 blocks。
- 鼠标悬停显示 bucket 内 evicted/rebuilt/hit 的数量。

### Timeline 视图

横轴：elapsed time。  
纵轴：block id 或 block bucket。  
点/短线颜色：事件后的状态。  

这张图适合对比策略：

- LRU：红色 evicted 点持续出现在热 family 的 block 上。
- shared-aware：绿色/青色块更稳定，红点减少。
- family-protect：受保护前缀有更长连续保留区间。

### Replay 输出

建议支持三种输出：

```bash
python experiments/long_pressure_benchmark/dashboard/render_replay_gif.py \
  --run-root <run_root> \
  --policy shared_aware \
  --output replay_shared_aware.gif \
  --duration-seconds 20 \
  --fps 20
```

输出文件：

```text
<run_root>/visuals/replay_lru.gif
<run_root>/visuals/replay_shared_aware.gif
<run_root>/visuals/replay_family_protect.gif
<run_root>/visuals/replay_comparison.mp4
```

GIF 用于汇报 PPT。MP4 用于更高质量播放。

## 视觉设计

页面主题：

- 背景：`#0b1020`
- 面板：`rgba(15, 23, 42, 0.72)`
- 边框：`rgba(148, 163, 184, 0.18)`
- 正常：`#22c55e`
- 压力：`#f59e0b`
- 错误/evicted：`#ef4444`
- prefix hit：`#38bdf8`
- rebuilt：`#a855f7`
- shared：`#34d399`

布局风格：

- 顶部指标卡不超过两行，避免信息堆满。
- 曲线图优先显示趋势，不把所有指标塞在一个图里。
- Replay 区域占页面视觉中心，宽度至少 60%。
- 输入输出样本放右侧抽屉或 expander，默认折叠。
- request class 使用固定颜色，方便汇报时快速识别。
- 所有时间都显示相对时间和最后更新时间。

推荐 tab：

```text
Live Overview | KV Cache Replay | Requests | Policy Compare | Logs
```

## 当前日志是否足够

### 已经足够的部分

1. 实时吞吐和延迟  
   `rolling_metrics.jsonl` 每 30 秒记录 completed、offered、req/s、tok/s、avg latency、p95 latency、errors。足够画主曲线。

2. KV pressure 和 prefix metrics  
   `prometheus_cache_samples.jsonl` 已经包含 `vllm:kv_cache_usage_perc`、running/waiting、prefix cache queries/hits 等 Prometheus 文本。足够画 cache pressure 和 prefix hit 趋势。

3. KV block 生命周期  
   `kvfabric_lifecycle.jsonl` 有 `block_allocated`、`block_sealed`、`block_touched`、`ref_count_changed`、`block_evicted`。字段包括 block id、state、prefix depth、hit count、share degree、retain score、family id、regret。足够重建 block 状态动画。

4. 策略证据  
   lifecycle 里已经有 admission、defer、promotion、latency promotion、rebuilt-from-eviction 等事件。足够解释策略为什么生效。

5. 输入请求  
   `trace.jsonl` 和 `trace/prompts/*.json` 能恢复每个 trace request 的 class、family、priority、max_tokens 和 prompt 内容。

### 还不够的部分

1. trace request id 和 vLLM request id 没有稳定映射  
   `raw_outputs_sample.jsonl` 记录的是 trace request id，`kvfabric_lifecycle.jsonl` 里是服务端 `chatcmpl-*` request id。现在很难把一次 prefix lookup、一次 block rebuild 和某条 trace 输入输出精确连起来。

   建议新增 header：

   ```text
   x-kvfabric-trace-request-id: req-000123
   ```

   然后在 `KVFabricRequestHints` 和 lifecycle event 里记录 `hint_trace_request_id`。

2. rolling metrics 没有 class 维度  
   final 的 `class_metrics.json` 有 class 维度，但实时 rolling 只有整体指标。Sticky 实验想实时观察 `decode_heavy_noise` 是否变好，需要 rolling class metrics。

   建议新增：

   ```text
   online_trace/rolling_class_metrics.jsonl
   ```

   每 30 秒写每个 request class 的 completed、tok/s、avg/p95 latency、SLO miss。

3. 输出采样不稳定  
   当前 sample rate 是 0.02，早期或异常退出时 `raw_outputs_sample.jsonl` 可能为空。面板需要能显示“当前没有采样命中”。为了展示效果，建议 dashboard 模式把 sample rate 提到 0.10 或至少保证每个 request class 采样 N 条。

4. raw output 没有输入摘要  
   输入可以从 trace 反查，但实时联动会多一次文件查找。建议在 raw sample 中额外写：

   ```json
   {
     "prompt_ref": "prompts/req-000123.json",
     "prompt_chars": 8231,
     "prompt_excerpt": "...",
     "expected_reuse": "durable",
     "cache_priority": "high"
   }
   ```

5. lifecycle 缺少周期性 snapshot  
   JSONL 能重建状态，但 dashboard 中途打开时需要从头读大文件。4h/12h raw lifecycle 文件可能很大。建议增加 `kvfabric_block_snapshot.jsonl`，或者 dashboard 第一次打开时只读最近 N MB 并标注为 partial replay。

6. job 状态不够明确  
   当前 job log 能看到 server ready，但如果 loadgen 提前退出，缺少明确 `policy failed` / `policy completed` 状态文件。建议 benchmark runner 写：

   ```text
   <run_root>/run_state.json
   <run_root>/<policy>/policy_state.json
   <run_root>/<policy>/heartbeat.json
   ```

   内容包括 phase、pid、started_at、last_update_at、exit_code、error_message。

7. `time_ns` 不能直接和 wall-clock 对齐  
   lifecycle 用 monotonic ns。单 policy 内 replay 没问题，但和 Prometheus/rolling metrics 对齐时需要 wall-clock start。建议 `tracker_initialized` 增加：

   ```json
   {
     "wall_time_seconds": 1782565092.123,
     "monotonic_time_ns": 24123456789
   }
   ```

8. 需要容忍脏尾部  
   当前一次早停 run 的 lifecycle tail 中出现了 NUL 字节。dashboard parser 不能因为一行坏数据崩掉。实现时要按行 parse，失败行计数，并继续处理下一行。

## 对现有实验脚本的建议改动

### online_trace_loadgen.py

建议新增：

- header `x-kvfabric-trace-request-id`
- `rolling_class_metrics.jsonl`
- `in_flight`、`pending_tasks`、`sampled_outputs`
- raw output 中记录 prompt excerpt 和 prompt_ref
- dashboard 模式下按 class 做保底采样

### kvfabric_hints.py / kvfabric_lifecycle.py

建议新增 hint 字段：

- `trace_request_id`

并在所有 request 级事件里输出：

- `hint_trace_request_id`
- `hint_request_class`
- `hint_family_key`
- `hint_cache_priority`
- `hint_expected_reuse`

### run_remote_27b_trace_long_benchmark.sh

建议新增：

- `run_state.json`
- `policy_state.json`
- `heartbeat.json`
- policy start/end/error 明确落盘
- 可选 `KVFABRIC_DASHBOARD=1` 自动启动 dashboard

### sync_remote_27b_benchmark_results.sh

建议新增：

- `INCLUDE_VISUALS=1`
- `INCLUDE_SNAPSHOTS=1`
- 默认同步 GIF/MP4 和 dashboard summary
- raw lifecycle 仍默认不同步，除非显式 `INCLUDE_RAW_JSONL=1`

## 实现顺序

第一阶段：只读 dashboard

- 新增 `run_kvfabric_dashboard.py`
- 能读取现有 run 目录和 job log。
- 能展示 rolling metrics、Prometheus、trace、raw outputs、lifecycle counters。
- 能做简化 block grid replay。
- 不改 benchmark 逻辑。

第二阶段：补日志字段

- 增加 trace request id header。
- 增加 rolling class metrics。
- 增加 run_state / policy_state / heartbeat。
- 增加 raw sample prompt excerpt。

第三阶段：离线 GIF/MP4

- 新增 `render_replay_gif.py`。
- 支持单策略 GIF。
- 支持三策略并排 MP4。
- 输出到 `<run_root>/visuals`。

第四阶段：一键远程启动

- `run_remote_27b_dashboard.sh`
- `start_remote_27b_sticky_with_dashboard.sh`
- 文档中写清端口转发命令。

## 验收标准

实时 dashboard：

- 打开页面 5 秒内能看到 run 状态。
- 运行中每 2-5 秒刷新一次。
- rolling metrics、Prometheus、lifecycle 任何一个缺失时页面不崩。
- 能显示当前 policy 和完成进度。
- 能显示至少一条输入 prompt 摘要。
- 有输出采样时能显示输出；没有采样时明确说明。
- 能显示 block grid replay。

离线 replay：

- 对任意一个有 `kvfabric_lifecycle.jsonl` 的 policy 生成 GIF。
- GIF 长度默认 20 秒。
- 至少包含状态颜色、时间、policy、prefix hit、evicted、rebuilt、admission saved。
- LRU 和 shared-aware 对比时，能直观看出 evicted/rebuilt 差异。

报告展示：

- 一张 dashboard 截图展示实时实验。
- 一个 20 秒 GIF 展示 KV cache 生命周期。
- 一张三策略对比表展示最终指标。
- 一段结论说明：吞吐证明实验看 tok/s；Sticky Conversation 看延迟和 tail；KV replay 证明生命周期管理确实改变了 cache 行为。

## 2026-06-28 实现更新

本轮已经把上面的主要入口落到代码中：

- `dashboard/run_kvfabric_dashboard.py`：Streamlit 实时面板，包含总览、KV Cache Replay、请求样本、策略对比、日志五个 tab。
- `dashboard/kvfabric_run_reader.py`：统一读取 run 目录、rolling metrics、Prometheus 采样、final metrics、raw sample、job log 和 trace prompt。
- `dashboard/kv_cache_replay.py`：按 lifecycle event 重建 block 状态，输出 block grid 和 event timeline。
- `dashboard/render_replay_gif.py`：离线导出单策略 replay GIF。
- `scripts/run_remote_27b_dashboard.sh`：在 robowalker 上启动 dashboard，默认检查并安装 `dashboard/requirements.txt`。
- `scripts/start_remote_27b_sticky_with_dashboard.sh`：启动 Sticky 4h 实验后自动打开 dashboard。
- `scripts/export_kv_cache_replay.sh`：从远程 run 导出 replay GIF。

日志字段也补了一轮：

- loadgen 请求头新增 `x-kvfabric-trace-request-id`，并传到 vLLM tracing。
- `KVFabricRequestHints` 新增 `trace_request_id`，lifecycle request meta 记录 `hint_trace_request_id`。
- `rolling_metrics.jsonl` 增加 prompt tok/s、completion tok/s、goodput tok/s、SLO miss rate。
- 新增 `rolling_class_metrics.jsonl`，实时记录各 request class 的 completed、tok/s、goodput、avg/p95 latency、SLO miss。
- `raw_outputs_sample.jsonl` 增加 tenant、session、family、turn、expected reuse、cache priority、phase、max tokens、prompt ref、prompt chars、message count、prompt excerpt。
- 长测 runner 新增 `run_state.json`、`policy_state.json`、`heartbeat.json`。server 启动失败、loadgen 失败、lifecycle 缺失都会明确落盘为 failed。

这次还修了一个脚本可靠性问题：`run_policy` 被 `if ! run_policy` 包住时，Bash 不应依赖 `set -e` 传播内部命令失败。现在 vLLM server 启动和 loadgen 退出码都显式捕获，失败后不会继续进入 metrics 阶段伪装成正常运行。

昨天 20:56 左右的 Sticky 4h run 说明了为什么需要这些状态文件。远程目录里只有 lru 的早期 rolling 和 lifecycle 文件，没有 final `metrics.json`，没有 shared-aware/family-protect 结果，job log 停在 server ready 附近。按新的 reader 规则，这类 run 应显示为 partial/stalled，而不能算作 4h 完整结果。

还有两个后续项没有放进本轮代码：

- `kvfabric_block_snapshot.jsonl`：现在 replay 可以读 lifecycle JSONL，但 dashboard 中途打开大文件时仍可能慢。后续可以在生命周期 logger 里周期性写 block snapshot。
- 三策略并排 MP4：当前先支持单策略 GIF。报告需要更强对比时，再把三个 policy 的 frame 合成一个 MP4。
