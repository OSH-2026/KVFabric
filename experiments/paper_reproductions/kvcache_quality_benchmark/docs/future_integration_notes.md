# Future Integration Notes

## 当前状态

当前目录已经具备：

- 可运行的 offline 质量评测脚本
- 可切换的 variant 配置
- 可复用的 suite / plan / run 输出结构
- 统一的汇总脚本

## 未来如何接入真实 candidate

如果后续已经有某种 KV 压缩、裁剪或量化实现，建议按下面步骤接入：

1. 复制 `variants/candidate_template.env`
2. 改出新的 variant 名称与说明
3. 如果需要额外 runtime 开关，先在脚本层补支持
4. 把新 variant 加进 `plans/*.env`
5. 运行 suite，查看 `suite_summary.md`

## 何时需要扩展脚本参数

当前脚本只覆盖比较基础的 runtime 参数。如果未来 candidate 需要更多控制项，例如：

- 自定义量化开关
- 不同 block size
- 特定压缩阈值
- 自定义 patch / 分支版本

建议优先扩展 `scripts/run_quality_variant.sh` 的 override 参数，再传给 `examples/offline_quality_eval.py`。

## 何时需要升级评分方式

当出现下面任一情况时，说明需要升级任务评分：

- 规则匹配太宽松，无法区分轻微退化和严重退化
- 模型输出风格变化大，关键词规则不稳定
- 需要与论文中的 accuracy / pass@k / exact match 更对齐

可选升级方向：

- 更严格的 exact match
- 结构化 JSON 输出比对
- 代码执行型单元测试
- 人工抽样复核
