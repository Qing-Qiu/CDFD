# CDFD Path Generator 功能增强说明

本文档说明在 CDFD Path Generator 项目上新增的**并行路径符号化表达**、**多输入同步分析**与**前端可视化**能力。原有线性路径生成、路径关系推断、Web UI 等能力均保留，并与新功能并存。

---

## 一、背景与问题

### 1.1 原有局限

| 问题领域 | 原有实现 | 不足 |
|---------|---------|------|
| **路径模型** | `PathResult` 仅为 `nodes[]`、`edges[]` 线性列表 | Fork 并行只能拆成多条独立路径 P1、P2，无法在单条路径对象中表达「同时发生」 |
| **并行关系** | `path_groups.py` 用极大团（Bron-Kerbosch）事后推断 `parallel` | 属于拓扑猜测，不是路径级 DAG / 偏序结构 |
| **多输入** | `find_paths` 对每个 `start` 独立 DFS | 只覆盖 OR 型多入口；无法处理 AND 型同步 Join |
| **前置条件** | `PathResult.preconditions` 常为空 | 多输入交汇处无法自动合并 C₁、C₂ |
| **可视化** | SVG 静态渲染 | 无法区分并行边，无数据流动画 |

### 1.2 改造目标

1. 用树 / 网结构表达嵌套并行（如 `n₁ → [n₂ ∥ n₃] → n₄`）
2. 用多 Token 状态推进支持 AND 多输入同步触发
3. 在 Web UI 用树状文本 + SVG 流光动画展示并行与多输入

---

## 二、新增数据模型（`models.py`）

### 2.1 `ConcurrentPathNode` — 并发路径树节点

```python
class ConcurrentPathNode(BaseModel):
    kind: str          # "node" | "sequential" | "parallel"
    node_id: str | None = None
    children: list[ConcurrentPathNode] = []
    label: str | None = None
```

| `kind` | 含义 | 结构 |
|--------|------|------|
| `node` | 单个图节点 | `node_id` 有值，`children` 为空 |
| `sequential` | 顺序执行 | `children` 为按序子节点 |
| `parallel` | 并行分支 | `children` 为同时执行的子路径 |

### 2.2 `ConcurrentPathResult` — 完整并发场景路径

除嵌套树 `root` 外，还包含扁平字段（便于导出与检索）：

- `nodes`、`edges`、`data`、`outputs`
- `preconditions`、`conditions`
- `notation`：符号化文本（如 `IN -> A -> [ B || C ] -> OUT_X4 -> OUT_X5`）

### 2.3 其他扩展

- **`PathResult.concurrent`**：可选字段，挂载对应并发树
- **`FunctionalScenario`**：新增 `concurrent_path`、`notation`；`kind` 可为 `concurrent`
- **`CDFDGraph.get_node_required_inputs()`**：根据 `ProcessSpec.inputs`、`input_ports` 或入边 `data` 推导节点必需输入

---

## 三、核心算法（`path_finder.py`）

### 3.1 `can_activate_node()` — 多输入激活判定

```python
def can_activate_node(graph, node_id, available_data, processes) -> bool:
    required = graph.get_node_required_inputs(node_id, processes)
    return required.issubset(available_data)  # AND 语义
```

**判定逻辑：**

1. 若存在 `input_ports`，端口内输入按 AND 检查，多个端口按 XOR 检查
2. 否则若存在 `ProcessSpec.inputs`，以 `inputs` 为必需数据集合
3. 否则收集所有非 control 入边的 `data`
4. 仅当所选端口或必需输入被 `available_data` 覆盖时返回 `True`

**示例（`examples/join.json`）：**

- `Combine` 需要 `{l_done, r_done}`
- 仅有 `l_done` → 不激活
- 两者齐全 → 可激活

### 3.2 `find_concurrent_paths()` — 多 Token 状态搜索

替代「单点 DFS」的主并发分析入口，返回 `list[ConcurrentPathResult]`。

#### 搜索状态 `_TokenState`

| 字段 | 含义 |
|------|------|
| `tokens` | 当前激活节点集合（多 Token） |
| `available_data` | 已产生的数据流 |
| `activated_nodes` | 已完全激活的节点 |
| `edges` / `data` | 已遍历的边与数据 |
| `conditions` / `preconditions` | 控制条件与前置条件 |
| `trace` | 用于构建并发树的轨迹 |

#### 初始状态策略

| 场景 | 策略 | 示例 |
|------|------|------|
| **OR 多输入** | 每个 `start` 独立初始任务 | 单源触发（线性路径语义） |
| **AND 多输入** | 单任务，初始 `tokens = 所有 start` | `data_store.json`：`{IN, PROFILE_STORE}` 同步启动 |

**AND 多输入检测条件：**

- `graph.metadata.start_sync == true`
- 或存在多输入进程，且多个 `start` 分别连到该进程

#### 推进规则

1. **并行分叉**：在显式 `parallel` / `fork` 结构处，或同一输出端口内无边条件冲突的多出边时，同时激活所有分支
2. **互斥选择**：显式 `choice` 结构，或边上条件互斥时，不并行分叉
3. **汇合 Join**：边到达目标但数据未齐时，移除 Token、保留数据；全部就绪后由 `_activate_ready_join_nodes()` 激活目标
4. **多 Token 同步步进**：`_advance_all_tokens()` 在同一步内推进所有活跃 Token
5. **去重**：按 `(edges, activated_nodes)` 合并重复结果

#### 与原有 `find_paths()` 的关系

- **`find_paths()`**：保留线性 DFS，兼容现有测试与 CLI
- **`find_concurrent_paths()`**：负责并发场景与 AND 同步分析
- 线性路径的 `preconditions` 合并逻辑已增强（多输入控制条件汇入）

---

## 四、并发路径工具模块（`concurrent_paths.py`）

| 函数 | 作用 |
|------|------|
| `format_notation()` | 树 → 符号文本，如 `[ IN \|\| PROFILE_STORE ] -> BuildResponse -> OUT` |
| `format_tree_lines()` | 树 → UI 控制台风格文本 |
| `normalize_concurrent_tree()` | 规范化并发树，合并嵌套 sequence 并去除连续重复汇合节点 |
| `build_concurrent_tree_from_paths()` | 从线性路径 + `PathRelation` 构建并发树 |
| `build_concurrent_results_from_relations()` | 从并行关系批量生成 `ConcurrentPathResult` |
| `flatten_nodes()` | 将树扁平化为节点列表 |

**树状文本示例：**

```text
▼ Scenario 1 Concurrent Path
  ├── IN
  ├── Split
  ├──══▼ PARALLEL BRANCHES
  │    ├── Branch A: L
  │    │   └── L
  │    └── Branch B: R
  │        └── R
  ├── Combine
  └── OUT
```

---

## 五、场景与导出

### 5.1 `scenarios.py`

`build_functional_scenarios()` 增强：

- 新增参数：`concurrent_paths`、`path_relations`
- 优先生成 `kind="concurrent"` 的 `FunctionalScenario`
- `description` 为树状文本；`notation` 为符号表达式
- 已被并发场景覆盖的路径不再重复生成单路径场景

### 5.2 `exporters.py`

- **`concurrent_paths_to_dicts()`**：序列化并发路径，含 `id`（CP1、CP2…）、`tree_lines`

---

## 六、Web API（`web.py`）

分析流程在原有路径生成后增加：

```text
find_concurrent_paths() → format_tree_lines() → build_functional_scenarios() → concurrent_paths_to_dicts()
```

**`POST /api/analyze` 响应新增字段：**

```json
{
  "paths": [...],
  "concurrent_paths": [
    {
      "id": "CP1",
      "notation": "IN -> Split -> [ L || R ] -> Combine -> OUT",
      "root": { "kind": "sequential", "children": [...] },
      "tree_lines": ["▼ Concurrent Path 1", "  ├── IN", ...],
      "edges": ["e1", "e2", "e3", "e4", "e5", "e6"],
      "preconditions": [],
      "conditions": []
    }
  ],
  "path_relations": [...],
  "functional_scenarios": [...]
}
```

命令行的 JSON / text / Markdown 输出也包含 `concurrent_paths` 或 `Concurrent Paths` 区块，与 Web API 保持同一套语义。

---

## 七、前端可视化（`templates/index.html`）

### 7.1 布局调整

- **Concurrent paths**：并发路径树（新增，置顶）
- **Linear paths**：原有线性路径列表
- **Path relations**：路径关系（可点击）

### 7.2 静态树状展示

- 使用后端 `tree_lines`，以 monospace 字体展示
- 并发项左侧蓝色边框标识
- 显示 `notation` 与条件信息

### 7.3 SVG 流光动画

点击 **Concurrent path** 或 **parallel 关系** 时：

- 相关边添加 class `parallel-active-edge`
- 并行边同时呈现蓝色流光动画，模拟 Token 并发传递
- 支持带图层前缀的边 ID（如 `Top:e2`）

```css
@keyframes flow {
  to { stroke-dashoffset: -20; }
}
.parallel-active-edge {
  stroke: #1890ff;
  stroke-width: 3px;
  stroke-dasharray: 5, 5;
  animation: flow 1s linear infinite;
}
```

---

## 八、验证用例与预期结果

| 示例文件 | 场景 | 并发路径 notation |
|---------|------|-------------------|
| `examples/cdfd_v1.json` | A 后 Fork 为 B、C | `IN -> A -> [ B \|\| C ] -> OUT_X4 -> OUT_X5` |
| `examples/join.json` | L、R 并行后 Join 到 Combine | `IN -> Split -> [ L \|\| R ] -> Combine -> OUT` |
| `examples/data_store.json` | IN 与 PROFILE_STORE 同步输入 | `[ IN \|\| PROFILE_STORE ] -> BuildResponse -> OUT` |

**测试文件：**

- `tests/test_concurrent_paths.py`
- `tests/test_cli.py`
- `tests/test_scenarios.py`
- `tests/test_exporters.py`
- `tests/test_examples.py`

**当前验证：** `python -m pytest -q` 通过，结果为 83 passed、1 个 FastAPI TestClient 兼容性 warning。

---

## 九、涉及文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/cdfd/models.py` | 修改 | 新增 `PortSpec`、`ConcurrentPathNode`、`ConcurrentPathResult` 等 |
| `src/cdfd/path_finder.py` | 扩展 | port-aware `can_activate_node`、`find_concurrent_paths`、多 Token 搜索 |
| `src/cdfd/concurrent_paths.py` | 新增 | 树构建、符号化、树状文本、并发树规范化 |
| `src/cdfd/consistency.py` | 修改 | 一致性检查支持 `input_ports` / `output_ports` |
| `src/cdfd/parsers/__init__.py` | 修改 | JSON 解析支持 process port |
| `src/cdfd/scenarios.py` | 修改 | 并发功能场景生成 |
| `src/cdfd/exporters.py` | 修改 | `concurrent_paths_to_dicts`，导出并发路径，路径 route 使用真实边端点/数据 |
| `src/cdfd/web.py` | 修改 | API 返回 `concurrent_paths` |
| `src/cdfd/cli.py` | 修改 | CLI 输出并发路径 |
| `src/cdfd/templates/index.html` | 修改 | 并发面板、树 UI、边动画 |
| `src/cdfd/multilevel.py` | 修改 | 多层展开保留 edge source/target/data 元数据 |
| `docs/cdfd-json-schema.json` | 修改 | JSON Schema 支持 `input_ports` / `output_ports` |
| `examples/port_alternatives.json` | 新增 | 多输入端口互斥示例 |
| `tests/test_concurrent_paths.py` | 新增 | 并发路径单元测试 |
| `tests/test_cli.py` | 新增 | CLI JSON 并发路径输出测试 |

---

## 十、架构对比

```text
【改造前】
CDFD 图 → 单源 DFS → 多条线性 PathResult
         → Bron-Kerbosch 事后推断 parallel 关系
         → 前端只显示 P1、P2 线性列表

【改造后】
CDFD 图 → find_paths()            → 线性 PathResult（兼容保留）
         → find_concurrent_paths() → ConcurrentPathResult（嵌套并行树）
         → path_groups 关系分析     → 与并发树互补
         → 前端：并发树 + 线性路径 + 并行边动画
```

---

## 十一、符号表达对照

| 语义 | 线性表达（旧） | 并发表达（新） |
|------|---------------|---------------|
| 并行分叉 | P1: n₁→n₂→n₄，P2: n₁→n₃→n₄ | n₁ → [ n₂ \|\| n₃ ] → n₄ |
| AND 多输入 | 两条独立不完整路径 | [ start_A \|\| start_B ] → Process → End |
| Fork + Join | 两条路径 + joined-output 关系 | 单条并发路径含 parallel 与 join 节点 |

---

## 十二、已知边界与后续方向

### 当前边界

1. **多层展开（multilevel）** 的并发分析主要在入口图层；深层子图未完全与 `find_concurrent_paths` 统一
2. **多终点并行**：如 `OUT_X4` 与 `OUT_X5` 在 notation 中可能仍为顺序表达，未完全写作 `[ OUT_X4 \|\| OUT_X5 ]`

### 可扩展方向

- 多层 process 展开的并发路径统一
- 终点并行分支的符号化完善
- 更多真实 SOFL `.cdfd` 文件的端口映射验证

---

## 十三、运行方式

```powershell
cd E:\WebProjects\CDFD
pip install -r requirements.txt
pip install -e .
python -m cdfd.web
```

浏览器访问：`http://127.0.0.1:8000`

在 Web UI 中点击 **Generate Paths** 后，左侧可查看 **Concurrent paths** 树状列表；点击并行关系或并发路径项，右侧 SVG 图中对应边将呈现流光动画。

---

## 总结

本次增强在保留原有线性路径能力的基础上，引入了嵌套并发路径模型、多 Token AND 同步搜索，以及 Web 端的树状展示与并行边流光动画，使 Fork、Join、多输入同步等场景能在路径层面被形式化表达和可视化，而不仅依赖事后的路径关系推断。
