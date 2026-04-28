# Experiments

`experiments/` 用来统一管理 KVFabric 的各类实验资产，但不再把所有阶段的内容直接平铺在根目录。

当前采用按“实验类型 / 阶段”分层的结构，方便后续继续扩展正式 benchmark 和论文复现：

```text
experiments/
├─ prebenchmark_validation/   baseline 跑通后的预基准验证套件
├─ benchmarks/                正式 benchmark、对照矩阵与批量结果
└─ paper_reproductions/       论文方法复现与对应实验材料
```

## 当前入口

- `prebenchmark_validation/`
  当前最成熟的实验套件，覆盖离线批量、在线 smoke、共享前缀 smoke、中等体量 prefix reuse 和日志摘要。

- `benchmarks/`
  预留给后续正式 benchmark。建议按“基线 / 改造版 / 对照配置”继续分层。

- `paper_reproductions/`
  预留给论文方法复现。建议按论文名或机制名建子目录，并保留配置、脚本、原始输出和分析结论。

## 建议约定

- 新增实验时，优先放到对应子目录，不再直接往 `experiments/` 根目录堆脚本。
- 每个子目录至少包含：
  - 一份 `README.md`
  - `configs/`、`scripts/`、`runs/` 或同等职责的目录
  - 可复现命令和输出目录约定
- 代表性结论可以整理进 `docs/`，但原始实验入口和过程文件保留在 `experiments/` 下。
