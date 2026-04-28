# Paper Reproductions

本目录预留给论文方法复现。

建议按论文名、方法名或机制名建子目录，并在每个复现目录中保留：

- 论文信息与目标
- 复现范围说明
- 配置文件
- 运行脚本
- 原始结果
- 偏差说明与结论

推荐结构：

```text
paper_reproductions/
└─ <paper_or_method_name>/
   ├─ README.md
   ├─ configs/
   ├─ scripts/
   └─ runs/
```

## 当前已落地目录

- `kvcache_quality_benchmark/`
  对应 `/work` 中“KVCache 压缩与质量评测”的第一版通用流程。当前重点是先把任务集、variant 接口、逐题评分和 suite 汇总做成可复用入口，方便后续真正接入 KV 压缩/量化实现。
