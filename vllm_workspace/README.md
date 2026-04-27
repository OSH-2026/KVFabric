# vLLM 源码工作区

本目录用于管理 vLLM v0.19.0 的 Python 控制面改造准备。

它不是一个可直接导入的 `vllm` Python 包，也不应该通过 `PYTHONPATH` 覆盖当前安装的 vLLM。这里采用 overlay 工作流：只把后续最可能修改的核心文件复制进当前项目，方便阅读、diff 和 patch 管理；真正运行时仍然应用到完整的上游源码工作树。

完整上游源码当前默认位于：

```text
/home/qy-dream/OSH_Project/vllm-v0.19.0
```

## 为什么使用 Overlay

如果只复制一部分 `vllm/` 包到 `KVFabric` 并直接导入，很容易遮蔽完整安装包，导致缺文件、导入混乱或运行时行为不一致。

Overlay 的好处是：

- 当前项目只管理后续要关注的核心文件；
- 不把半成品源码伪装成完整 vLLM 包；
- 可以清楚比较 upstream 与本地改动；
- 后续能导出 patch 或应用到完整源码树运行。

## 第一批关注文件

当前 overlay 聚焦 Python 控制面：

- `vllm/v1/core/block_pool.py`
- `vllm/v1/core/kv_cache_manager.py`
- `vllm/v1/core/kv_cache_metrics.py`
- `vllm/v1/core/kv_cache_utils.py`
- `vllm/v1/core/single_type_kv_cache_manager.py`
- `vllm/v1/core/kv_cache_coordinator.py`
- `vllm/v1/core/sched/scheduler.py`
- `vllm/v1/core/sched/output.py`
- `vllm/v1/metrics/stats.py`

这些文件覆盖 prefix cache 命中、block 分配、free queue、驱逐、KV cache 统计和调度输出，是后续添加生命周期日志和共享感知策略的优先位置。

## 常用命令

```bash
cd KVFabric

bash vllm_workspace/scripts/sync_from_upstream.sh
bash vllm_workspace/scripts/diff_to_patch.sh
bash vllm_workspace/scripts/apply_to_worktree.sh
```

建议流程：

1. 从上游同步 overlay。
2. 在 overlay 中做小步修改。
3. 导出 patch 审查。
4. 应用到完整 `vllm-v0.19.0`。
5. 用 `experiments/` 里的当前阶段测试验证行为。

