# CDFD 多输出标准改造说明

在最新 `origin/main`（含 `output_ports`、并发树规范化等能力）之上，补充**多 sink 流分解**与**多产出打包**能力。

## 核心改造

| 模块 | 内容 |
|------|------|
| Path Definition | `s → any sink`，`PathResult.sink` |
| 多输出打包 | `collect_path_outputs()` → `PathResult.outputs` |
| 流分解 | `FlowDecompositionResult`: `paths + cycles + flow_distribution` |
| 并发终点 | `normalize_parallel_end_nodes` → `[ OUT_A \|\| OUT_B ]` |
| Web API | 新增 `flow_decomposition` 字段 |

## 验证

```powershell
python -m pytest tests/test_multi_output.py -v
python -m cdfd.web
```

测试图：`examples/11_multi_output.json`

## 数据链路

```text
metadata.outputs / ProcessSpec.outputs
  → collect_path_outputs
  → PathResult.outputs / ConcurrentPathResult.outputs
  → decompose_project_flow → flow_distribution
  → build_functional_scenarios → output_data: [Data1, Data2]
```
