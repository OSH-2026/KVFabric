# KVFabric 长时间对话压测

云端模型扮演用户，与本地 vLLM 长时间对话，模拟真实场景并采集 KV Cache 生命周期指标。

---

## 参数配置指南

所有参数集中在 `config.json`，按区块说明每个字段的含义和如何修改。

### vllm — 本地 vLLM 服务连接

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `base_url` | string | vLLM 的 OpenAI 兼容端点 | 如果改了 vLLM 端口，这里同步改 |
| `model` | string | 请求中用的模型名 | 必须等于 vLLM 启动时的 `--served-model-name` |
| `temperature` | float | 生成温度，0=确定性输出 | 保持 0.0 保证可复现 |
| `max_tokens` | int | vLLM 单次回复的最大 token 数 | 模型支持越长设越大，但影响响应速度 |
| `timeout_seconds` | float | 请求超时秒数 | vLLM 慢时可加大 |

### cloud_user — 云端模型（扮演用户的 AI）

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `provider` | string | 仅标签，不影响逻辑 | 改成你用的厂商名，方便识别 |
| `model` | string | 云端模型名 | 换成你 API 支持的任意模型 |
| `base_url` | string | API 端点地址 | OpenAI 兼容即可。阿里百炼：`https://dashscope.aliyuncs.com/compatible-mode/v1`，DeepSeek：`https://api.deepseek.com/v1` |
| `api_key_env` | string | **环境变量名**，程序从中读取 API Key | 不要直接写 key！设为环境变量名，再用 `export 变量名="sk-xxx"` 注入 |
| `temperature` | float | 生成温度 | 建议 0.7–0.9，保证问题多样性 |
| `max_tokens` | int | 云端模型单次回复的最大 token 数 | 128 足够生成一个简短问题 |

切换云端模型的示例：

```json
// 阿里百炼（通义千问）
{ "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen3.7-plus", "api_key_env": "DASHSCOPE_API_KEY" }

// DeepSeek
{ "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY" }

// 本地模型
{ "base_url": "http://127.0.0.1:8000/v1", "model": "qwen3.5-2b-local", "api_key_env": "LOCAL_KEY" }
```

### conversation — 对话行为

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `mode` | string | 对话模式 | 可选：`continuous` / `random_topic` / `persona_rotation` / `dataset_driven` / `pressure_test` / `multi_turn_fork` |
| `total_rounds` | int | 总共跑多少轮 | 调大 = 更长时间测试。命令行 `--rounds` 可覆盖 |
| `share_rounds_history` | int | 云端模型能看到近几轮对话历史 | 越大云端提问越有上下文连贯性 |
| `vllm_system_prompt` | string | vLLM 的系统级指令 | 改成你想要的助手人设。共享前缀测试时部分模式会自动覆盖此值 |
| `max_context_tokens` | int | vLLM 对话历史超过此值自动截断旧消息 | 必须小于 vLLM 的 `max_model_len`。当前 vLLM 设为 1024，这里 900 留出 124 token 给回复 |
| `modes` | object | 各对话模式的子配置 | 见下方各模式说明 |

### conversation.modes.continuous — 持续追问

| 字段 | 类型 | 说明 |
|------|------|------|
| `initial_topic` | string | 起始话题 |
| `questions_per_topic` | int | 每个话题追问多少轮后切换 |

### conversation.modes.random_topic — 随机话题

| 字段 | 类型 | 说明 |
|------|------|------|
| `topic_pool` | list[string] | 候选话题列表，每轮随机选 |

### conversation.modes.persona_rotation — 角色轮换

| 字段 | 类型 | 说明 |
|------|------|------|
| `personas` | list[string] | 轮换的角色列表，可选：`大学生` / `面试官` / `debugger` / `产品经理` / `研究员` / `随便聊聊` |
| `rounds_per_persona` | int | 每个角色持续多少轮后切换 |

### conversation.modes.dataset_driven — 数据集驱动

| 字段 | 类型 | 说明 |
|------|------|------|
| `dataset` | string | 数据集名，对应 `datasets.sources[].name`，如 `sharegpt` 或 `lmsys_chat_1m` |
| `sample_strategy` | string | `sequential` 顺序采样 / `random` 随机采样 |
| `prefix_with_shared_system` | bool | 是否给所有 vLLM 请求注入同一个长 system prompt（制造 prefix cache 命中） |
| `shared_system_prompt` | string | 共享前缀文本。越长越好，建议 > 1 个 KV block |

### conversation.modes.pressure_test — 并发压力测试

| 字段 | 类型 | 说明 |
|------|------|------|
| `shared_prefix_ratio` | float | 共享前缀请求占比（0.0–1.0） |
| `shared_prefix_tokens` | int | 共享前缀约多少 token（文档参考值，实际由代码内嵌的共享前缀决定） |
| `cold_request_tokens` | int | 冷请求约多少 token（文档参考值） |
| `concurrency` | int | 每轮并发请求数。vLLM 的 `--max-num-seqs` 必须 >= 此值 |

### conversation.modes.multi_turn_fork — 分叉测试

| 字段 | 类型 | 说明 |
|------|------|------|
| `shared_turns` | int | 共享对话阶段多少轮 |
| `fork_branches` | int | 分叉为几个分支 |
| `private_turns` | int | 每个分支的私有对话轮数 |

### datasets — 数据集下载

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `cache_dir` | string | 数据集缓存目录 | 默认 `./data` |
| `sources` | list | 数据源列表 | 每个数据源包含以下字段 |

每个数据源（`sources[]`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 数据集名，`dataset_driven` 模式下用此名引用 |
| `url` | string | 下载地址。`format: "json"` 时是 HTTP URL，`format: "hf"` 时是 HuggingFace 仓库名 |
| `format` | string | `"json"` 直接下载 JSON / `"hf"` 从 HuggingFace Hub 下载 |
| `split` | string | 仅 HF 格式有效，如 `"train"` |
| `max_samples` | int | 仅 HF 格式有效，最大下载条数 |
| `fields` | object | 仅 JSON 格式有效，指定对话字段映射 |

### output — 运行输出

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `runs_dir` | string | 运行结果保存目录 | 默认 `./runs` |
| `save_dialogue` | bool | 是否保存完整对话 JSONL | 关掉可减少磁盘写入 |
| `save_metrics` | bool | 是否保存指标快照 | 关掉可减少磁盘写入 |
| `save_interval_rounds` | int | 每多少轮刷一次盘 | 值越小磁盘 I/O 越频繁但数据更安全 |
| `collect_kv_metrics` | bool | 是否采集 vLLM 的 `/metrics` 端点数据 | 开启后每个 snapshot_interval 采集一次 Prometheus 指标 |
| `metrics_url` | string | vLLM Prometheus 指标地址 | 默认 `http://127.0.0.1:8000/metrics` |

### display — 终端显示

| 字段 | 类型 | 说明 | 怎么改 |
|------|------|------|--------|
| `show_dialogue` | bool | 是否打印对话内容 | 长时间跑可关掉减少终端刷屏 |
| `show_status_bar` | bool | 是否显示状态栏 | — |
| `show_metrics_snapshot` | bool | 是否定期打印指标快照 | — |
| `snapshot_interval_rounds` | int | 每多少轮打印一次指标 | 值越小越频繁 |
| `color` | bool | ANSI 彩色输出 | 重定向到文件时可能乱码，关掉即可 |

---

## 目录

- [快速开始](#快速开始)
- [架构设计](#架构设计)
- [对话模式](#对话模式)
- [命令行用法](#命令行用法)
- [输出文件](#输出文件)
- [并发压力测试](#并发压力测试)
- [A/B 对比](#ab-对比)
- [文件结构](#文件结构)
- [常见问题](#常见问题)

---

## 快速开始

```bash
# 1. 依赖（项目 .venv 已包含 openai，如需 HF 数据集再加 datasets）
/home/llyun/KVcasha/.venv/bin/pip install openai

# 2. 设置云端 API Key
export DASHSCOPE_API_KEY="sk-xxx"

# 3. 启动 vLLM 服务（另开终端）
cd /home/llyun/KVcasha/vllm_baseline
bash scripts/serve_local.sh qwen3_5_2b

# 4. 运行对话压测（先试 3 轮验证链路）
cd /home/llyun/KVcasha/experiments/langtime_running_test
/home/llyun/KVcasha/.venv/bin/python3 run_dialogue.py --config config.json --rounds 3
```

---

## 架构设计

### 数据流

```text
┌─────────────┐     ┌──────────────────┐
│  config.json │────▶│  ConfigManager   │
└─────────────┘     └──────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │DatasetMgr│ │CloudModel│ │VLLMModel │
       │(按需下载)│ │(云端 API)│ │(本地vLLM)│
       └────┬─────┘ └────┬─────┘ └────┬─────┘
            │            │            │
            ▼            ▼            │
       ┌──────────────────────┐       │
       │   ConversationMode   │       │
       │ (生成对话指令/前缀)   │───────┘
       └──────────┬───────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │   DialogueManager    │
       │ (管理对话历史/截断)   │
       └──────────┬───────────┘
                  │
         ┌────────┼────────────┐
         ▼        ▼            ▼
    ┌────────┐┌──────────┐┌──────────────┐
    │Display ││ Recorder  ││MetricsScraper│
    │(终端)  ││(JSONL日志)││(Prometheus)  │
    └────────┘└──────────┘└──────────────┘
```

### 核心模块

| 模块 | 职责 |
|------|------|
| `config.py` | 加载 `config.json`，校验字段，准备运行目录 |
| `models.py` | 封装 `CloudModel`（云端 API）和 `VLLMModel`（本地 vLLM），使用 OpenAI SDK 直接调用 |
| `conversation.py` | `DialogueManager` 管理对话历史、`MetricsAccumulator` 累加延迟/吞吐指标 |
| `display.py` | 彩色终端输出：思考状态、对话内容、指标快照 |
| `modes/base.py` | `ConversationMode` 抽象基类，定义 `get_scene_instruction()`、`get_vllm_system_prompt()`、`get_batch_size()` 等钩子 |
| `modes/*.py` | 6 种对话模式实现（见下文） |
| `personas.py` | 6 个预设用户画像（大学生/面试官/debugger/产品经理/研究员/随便聊聊） |
| `datasets.py` | 数据集下载（JSON URL / HuggingFace Hub）与用户消息采样 |
| `recorder.py` | JSONL 对话日志 + 汇总指标输出 |
| `metrics_scraper.py` | 定期采集 vLLM Prometheus 指标（KV block 水位、prefix hit rate、eviction regret 等） |
| `retry.py` | 指数退避重试（云端 API 最多 3 次，vLLM 最多 2 次） |

### 一轮对话的完整生命周期

```text
1. mode.on_round_start()        → 模式更新内部状态（切换话题/角色/前缀）
2. dialogue.build_user_context() → 组装云端模型 context（场景指令 + 近 N 轮历史）
3. cloud_model.invoke()         → 云端模型生成用户问题
4. dialogue.add_user_message()  → 写入 vLLM 对话历史
5. mode.get_vllm_messages()     → 组装 vLLM 请求（可能注入共享前缀）
6. vllm_model.invoke()           → vLLM 生成回复
7. dialogue.add_assistant_message() → 写入 vLLM 对话历史
8. recorder.log_round()          → 落盘 JSONL
9. metrics_acc.record()          → 累加延迟/吞吐统计
10. dialogue.trim_history()      → 超出 context window 则截断旧消息
11. mode.on_round_end()          → 模式记录本轮结果
```

---

## 配置文件

所有参数集中在 `config.json`，主要分 6 个区块：

### vllm

```json
{
  "base_url": "http://127.0.0.1:8000/v1",
  "model": "qwen3.5-2b-local",      // 必须和 vLLM 启动时的 --served-model-name 一致
  "temperature": 0.0,                 // vLLM 生成温度（0 = 确定性输出）
  "max_tokens": 256,                  // vLLM 单次回复最大 token 数
  "timeout_seconds": 120
}
```

### cloud_user

```json
{
  "provider": "qwen3",               // 仅标签，不影响逻辑
  "model": "qwen3.7-plus",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key_env": "DASHSCOPE_API_KEY", // 从环境变量读取 API Key
  "temperature": 0.8,                 // 云端温度（高一点保证多样性）
  "max_tokens": 128
}
```

支持的云端 API（任意 OpenAI 兼容接口）：DeepSeek、阿里百炼（DashScope）、OpenAI、本地模型等，改 `base_url` + `model` + `api_key_env` 即可切换。

### conversation

```json
{
  "mode": "continuous",              // 对话模式
  "total_rounds": 200,               // 总轮数
  "share_rounds_history": 5,         // 云端模型可见的历史轮数
  "vllm_system_prompt": "...",       // vLLM 的系统级 prompt
  "max_context_tokens": 900,         // 超出则自动截断旧消息
  "modes": { ... }                   // 各模式的子配置
}
```

### datasets

```json
{
  "cache_dir": "./data",
  "sources": [
    {
      "name": "sharegpt",
      "url": "https://huggingface.co/.../ShareGPT_V3_unfiltered_cleaned_split.json",
      "format": "json",
      "fields": { "conversations": "conversations", "role_from": "from", "role_value": "value" }
    },
    {
      "name": "lmsys_chat_1m",
      "url": "lmsys/lmsys-chat-1m",
      "format": "hf",                // HuggingFace 格式
      "split": "train",
      "max_samples": 3000
    }
  ]
}
```

### output

```json
{
  "runs_dir": "./runs",
  "save_dialogue": true,
  "save_metrics": true,
  "save_interval_rounds": 20,
  "collect_kv_metrics": true,                                    // 是否采集 vLLM Prometheus 指标
  "metrics_url": "http://127.0.0.1:8000/metrics"
}
```

### display

```json
{
  "show_dialogue": true,             // 打印对话内容
  "show_status_bar": true,
  "show_metrics_snapshot": true,
  "snapshot_interval_rounds": 10,    // 每 N 轮打印一次指标快照
  "color": true                      // ANSI 彩色输出
}
```

---

## 对话模式

| 模式 | 命令参数 | 适用场景 | vLLM 前缀行为 |
|------|----------|----------|--------------|
| `continuous` | `--mode continuous` | 日常压测 | 使用 `vllm_system_prompt` |
| `random_topic` | `--mode random_topic` | 多样性测试 | 使用 `vllm_system_prompt` |
| `persona_rotation` | `--mode persona_rotation` | 多角色负载 | 使用 `vllm_system_prompt` |
| `dataset_driven` | `--mode dataset_driven` | 真实对话模拟 | `prefix_with_shared_system=true` 时注入长共享前缀 |
| `pressure_test` | `--mode pressure_test` | KV Cache 压力测试 | 共享请求注入长前缀，冷请求最简 prompt |
| `multi_turn_fork` | `--mode multi_turn_fork` | 分叉/CoW 行为验证 | 共享阶段注入长前缀，分叉后独立 prompt |

### continuous — 持续追问

围绕一个初始话题深入追问，每 `questions_per_topic` 轮后自动切换话题。

```json
"continuous": {
  "initial_topic": "Python 编程",
  "questions_per_topic": 6
}
```

### random_topic — 随机话题

每轮从 `topic_pool` 随机选话题。

```json
"random_topic": {
  "topic_pool": ["Python 编程", "算法与数据结构", "Linux 运维", ...]
}
```

### persona_rotation — 角色轮换

多个用户画像轮换，每个画像 `rounds_per_persona` 轮。

```json
"persona_rotation": {
  "personas": ["大学生", "面试官", "debugger", "产品经理"],
  "rounds_per_persona": 10
}
```

预设画像（`src/personas.py`）：大学生、面试官、debugger、产品经理、研究员、随便聊聊。

### dataset_driven — 数据集驱动

从 ShareGPT / LMSYS 等数据集中采样真实对话，供云端模型参考提问风格。

```json
"dataset_driven": {
  "dataset": "sharegpt",              // 或 "lmsys_chat_1m"
  "sample_strategy": "sequential",    // sequential | random
  "prefix_with_shared_system": true,  // 是否为所有 vLLM 请求注入共享前缀
  "shared_system_prompt": "..."       // 共享前缀文本（越长越好，建议 > 1 block）
}
```

### pressure_test — 并发压力测试

每轮同时发 N 个并发请求，其中 `shared_prefix_ratio` 比例带长共享前缀，其余为冷请求。

```json
"pressure_test": {
  "shared_prefix_ratio": 0.7,    // 70% 共享前缀
  "shared_prefix_tokens": 600,   // 共享前缀 token 数（供参考）
  "cold_request_tokens": 400,    // 冷请求 token 数（供参考）
  "concurrency": 4               // 每轮并发数
}
```

**重要**：vLLM 需要启动时设置 `--max-num-seqs` >= concurrency，否则并发请求会排队。

### multi_turn_fork — 分叉测试

模拟 CoW 分叉场景：前 `shared_turns` 轮共享前缀 → 分叉为 `fork_branches` 个分支 → 每个分支 `private_turns` 轮私有对话。

```json
"multi_turn_fork": {
  "shared_turns": 4,
  "fork_branches": 3,
  "private_turns": 3
}
```

---

## 命令行用法

### run_dialogue.py — 单次对话压测

```bash
# 默认 continuous 模式
python run_dialogue.py --config config.json

# 指定模式和轮数（CLI 参数覆盖 config.json）
python run_dialogue.py --config config.json --mode persona_rotation --rounds 200

# 安静模式（不打印对话内容，只显示状态和指标）
python run_dialogue.py --config config.json --no-display --rounds 500

# 跳过数据集下载（已缓存时）
python run_dialogue.py --config config.json --mode dataset_driven --skip-dataset-download
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config` | 配置文件路径 | 必填 |
| `--mode` | 覆盖对话模式 | 使用 config 中的值 |
| `--rounds` | 覆盖总轮数 | 使用 config 中的值 |
| `--no-display` | 关闭对话内容打印 | false |
| `--skip-dataset-download` | 跳过数据集下载 | false |

### run_compare.py — A/B 对比

```bash
# 对比 vanilla vs observe
python run_compare.py --config config.json --mode persona_rotation --rounds 100

# 三路对比
python run_compare.py --config config.json --mode multi_turn_fork --rounds 100 \
  --variants vanilla,observe,shared_aware
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config` | 配置文件路径 | 必填 |
| `--mode` | 对话模式 | 使用 config 中的值 |
| `--rounds` | 每轮对比的总轮数 | 使用 config 中的值 |
| `--variants` | 逗号分隔的策略列表 | `vanilla,observe` |
| `--no-display` | 关闭对话打印 | false |

三种 variant 环境变量：

| variant | `KVFABRIC_LIFECYCLE` | `KVFABRIC_LIFECYCLE_POLICY` |
|---------|----------------------|---------------------------|
| `vanilla` | 0 | — |
| `observe` | 1 | observe |
| `shared_aware` | 1 | shared_aware |

---

## 输出文件

每次运行在 `runs/<timestamp>/` 下生成：

```text
runs/2026-06-04_203638/
├── config.json                  # 本次运行实际使用的配置
├── dialogue.jsonl               # 完整对话记录（每行一个 JSON 对象）
├── metrics.jsonl                # 每 N 轮的延迟/吞吐快照
├── summary.json                 # 汇总指标
└── kv_metrics_snapshots.jsonl   # vLLM Prometheus 指标快照（需开启 collect_kv_metrics）
```

### dialogue.jsonl 字段

```json
{
  "round": 1,
  "user_label": "问答者(Python 编程)",
  "user_content": "我最近看源码发现到处都是装饰器...",
  "assistant_content": "带参数的装饰器之所以看起来像三层...",
  "cloud_latency_seconds": 15.3,
  "vllm_latency_seconds": 4.5,
  "vllm_tokens": 256,
  "timestamp": 1717518998.123
}
```

### summary.json 字段

```json
{
  "total_rounds": 200,
  "elapsed_seconds": 1200.5,
  "mode": "连续追问",
  "vllm_latency_avg": 4.2,
  "vllm_latency_median": 3.8,
  "vllm_latency_p95": 6.1,
  "vllm_tokens_avg": 220.5,
  "vllm_throughput_tok_s": 55.2,
  "cloud_latency_avg": 12.3,
  "generated_at": "2026-06-04 20:30:00 +0800"
}
```

### kv_metrics_snapshots.jsonl 字段

```json
{
  "round": 10,
  "timestamp": 1717518998.456,
  "kv_cache_usage_perc": 0.35,
  "kv_block_free": 120,
  "kv_block_total": 256,
  "kv_block_active": 45,
  "kv_block_peak_active": 52,
  "prefix_cache_hit_rate": 0.74,
  "kv_block_lookup_hit_rate": 0.68,
  "kv_block_evictions": 12,
  "kv_block_eviction_regrets": 2,
  "eviction_regret_rate": 0.167,
  "prompt_tokens_total": 15000,
  "prompt_tokens_cached": 11000,
  "prompt_tokens_recomputed": 4000,
  "running_requests": 1,
  "waiting_requests": 0
}
```

---

## 并发压力测试

### 启用并发

1. vLLM 启动时必须提高 `--max-num-seqs`：

```bash
# 修改 vllm_baseline/scripts/serve_local.sh，将 --max-num-seqs 1 改为 8
vllm serve ... --max-num-seqs 8
```

2. `config.json` 中设置 concurrency：

```json
"pressure_test": {
  "concurrency": 4,   // 每轮同时发 4 个请求
  ...
}
```

### 多终端并发

也可以在不同终端运行多个 `run_dialogue.py` 实例（每个实例是独立用户），但各实例的 conversation history 彼此独立，无法共享前缀。要实现真正的共享前缀并发压测，使用 `pressure_test` 模式更合适——多个线程在同一轮共享同一个 baseline 对话历史快照。

### 并发模型

```text
第 N 轮 batch:
  ┌─ 云端模型生成 4 个不同问题（一次 API 调用）
  │
  ├─ 线程1: question_1 → vLLM → reply_1  (共享前缀)
  ├─ 线程2: question_2 → vLLM → reply_2  (共享前缀)
  ├─ 线程3: question_3 → vLLM → reply_3  (共享前缀)
  └─ 线程4: question_4 → vLLM → reply_4  (冷请求，无共享)
  
  每个线程持有独立的对话历史快照，互不污染。
  ThreadPoolExecutor 等待所有线程完成，然后记录结果。
```

---

## A/B 对比

运行同一负载对比不同 KVFabric 策略：

```bash
python run_compare.py --config config.json --mode persona_rotation --rounds 100 \
  --variants vanilla,observe,shared_aware
```

输出示例：

```text
======================================================================
  A/B 对比结果  (persona_rotation, 100轮/变体)
======================================================================
变体                  成功轮    耗时(s)  avg延迟(s)    p95(s)      吞吐
----------------------------------------------------------------------
vanilla vLLM             98        430       4.320     6.120     54.2
KVFabric observe         97        438       4.510     6.350     53.1
KVFabric shared_aware    96        445       4.630     6.890     51.8

📁 对比结果已保存至: runs/compare/20260604_210000/
```

---

## 文件结构

```text
langtime_running_test/
├── README.md                       # 本文档
├── config.json                     # 主配置文件
├── requirements.txt                # Python 依赖
├── .gitignore
│
├── run_dialogue.py                 # 单次对话压测入口
├── run_compare.py                  # A/B 对比入口
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # 配置加载与校验
│   ├── models.py                   # CloudModel + VLLMModel (OpenAI SDK)
│   ├── retry.py                    # 指数退避重试
│   ├── display.py                  # 彩色终端输出
│   ├── conversation.py             # DialogueManager + MetricsAccumulator
│   ├── personas.py                 # 6 个预设用户画像
│   ├── datasets.py                 # 数据集下载与采样 (JSON/HF)
│   ├── recorder.py                 # JSONL 记录器
│   ├── metrics_scraper.py          # vLLM Prometheus 指标采集
│   └── modes/
│       ├── __init__.py
│       ├── base.py                 # ConversationMode 抽象基类
│       ├── continuous.py           # 持续追问
│       ├── random_topic.py        # 随机话题
│       ├── persona_rotation.py     # 角色轮换
│       ├── dataset_driven.py      # 数据集驱动 + 共享前缀注入
│       ├── pressure_test.py       # 并发压力测试 + 共享前缀注入
│       └── multi_turn_fork.py     # 分叉测试 + 共享前缀注入
│
├── data/                           # 数据集缓存（gitignore）
└── runs/                           # 运行输出（gitignore）
    ├── 2026-06-04_203638/          # 单次运行
    │   ├── config.json
    │   ├── dialogue.jsonl
    │   ├── metrics.jsonl
    │   ├── summary.json
    │   └── kv_metrics_snapshots.jsonl
    └── compare/20260604_210000/    # A/B 对比
        ├── vanilla/
        ├── observe/
        ├── shared_aware/
        └── compare_summary.json
```

---

## 常见问题

### Q: 云端模型返回空消息？
A: 确认 `api_key_env` 对应的环境变量已设置，且 `base_url` 是 OpenAI 兼容的 `/v1` 端点。

### Q: vLLM 返回 404 "model does not exist"？
A: `config.json` 中 `vllm.model` 的值必须和 vLLM 启动时的 `--served-model-name` 一致。

### Q: 并发压测时请求似乎在排队？
A: vLLM 启动参数 `--max-num-seqs` 限制了最大并发序列数，需要 >= `concurrency`。

### Q: 对话内容不显示/终端输出乱码？
A: 加 `--no-display` 关闭对话打印，或确认终端支持 UTF-8 和 ANSI 颜色。

### Q: LMSYS 数据集下载失败？
A: 需要安装 `datasets` 库：`pip install datasets`。如网络受限，可手动下载 JSON 放到 `data/` 目录。

### Q: 如何换云端模型？
A: 修改 `config.json` 中 `cloud_user` 的 `base_url`、`model`、`api_key_env` 三个字段即可。只要是 OpenAI 兼容 API 都支持。

### Q: Ctrl+C 中断后数据会丢失吗？
A: 不会。SIGINT 信号被捕获，中断前已完成的所有轮次都会写入 summary 和日志文件。
