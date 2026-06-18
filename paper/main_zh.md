# 面向 Conditional Data Flow Diagram 的端口感知并发路径生成器

作者姓名  
课程项目  
学院或系别  
邮箱：author@example.com

## 摘要

Conditional Data Flow Diagram（CDFD）通过数据流、process、控制条件和层次化 process 分解来描述软件行为。因此，从 CDFD 生成路径并不等同于枚举普通图路径。一个 process 可能有多个输入端口和输出端口，不同端口可能互斥，同一端口内的输入可能需要同时可用，互不依赖的分支也可能并发运行。本文提出一个 CDFD 路径生成工具：它接收完整的 CDFD 项目文件，将其转换成公共图模型，检查结构合法性，生成原子路径和并发路径，并可视化图与路径信息。论文定义路径模型，说明 JSON 和 SOFL `.cdfd` 解析方法，描述合法性检查与系统功能，详细展开不同 CDFD 情况下的端口感知算法，并用代表性 CDFD 输入对工具进行案例分析。

关键词：CDFD，SOFL，路径生成，并发路径，图分析，端口语义

## 1. 课题背景与意义

Conditional Data Flow Diagram（CDFD）用于 SOFL 风格的规格说明中，描述数据项如何进入系统、如何被 process 转换、如何被存储，并最终如何离开系统。与普通有向图相比，CDFD 具有更丰富的语义。边可能表示数据流、active data flow 或控制流。节点可能是 process、data store、state node、condition node 或 SOFL connector structure。高层 process 还可能分解为低层 CDFD。

本课程任务是设计一个工具：导入任意符合约定文件格式的 CDFD，并自动输出它的路径。任务要求输入文件包含工具所需的全部信息，因此生成结果不应依赖导入后的人工解释。任务也要求路径定义足够清楚，因为 CDFD 路径可能涉及并发和互斥 process 接口。

本课题有两方面意义。第一，它把非形式化的读图活动转化为有定义的图分析问题。读者可以追问一条路径为什么合法、两条分支为什么并行、为什么某一个输入不足以激活 process，而工具可以通过显式模型规则回答。第二，它支持 CDFD 审阅和教学。对于复杂图，学生不必完全手动沿箭头推演，而可以比较导入的 CDFD、生成的原子路径、并发路径、路径关系和一致性警告。

## 2. 方法概述

本节定义工具使用的基本对象，并说明整体方法：输入设计、CDFD 解析、合法性检查、路径生成和系统输出。

### 2.1 CDFD 项目定义

**定义 1（CDFD project）。**
一个 CDFD project 是元组：

```text
P = (M, S, G, g0)
```

其中，`M` 是 module 信息，`S` 是 process specification 集合，`G` 是命名 CDFD 图集合，`g0 in G` 是入口图。

**定义 2（CDFD graph）。**
一个 CDFD graph 是元组：

```text
G = (V, E, Vs, Vt, R)
```

其中，`V` 是节点集合，`E` 是有向边集合，`Vs` 是源节点集合，`Vt` 是汇节点集合，`R` 是显式结构集合，例如 parallel、fork、choice、join、merge 和 process decomposition hint。

**定义 3（edge）。**
一条边 `e in E` 具有源点 `src(e)`、目标点 `dst(e)`、类型 `kind(e)`、数据标签集合 `data(e)` 和可选条件 `cond(e)`。数据流和 active-flow 边可以被路径遍历。控制流边不是路径段，而是被收集为相关 process 的路径条件。

### 2.2 输入文件设计

标准项目格式是 `cdfd-json-v1`。它包含：

- `module`：常量、类型、变量和入口行为图；
- `processes`：process specification，包括输入/输出数据、端口、前置条件、后置条件和可选分解图名称；
- `graphs`：图层，每个图层包含节点、边、起点、终点和显式结构；
- `metadata`：可选布局信息或输入来源相关信息。

工具也导入 SOFL 桌面工具的 `.cdfd` XML 文件。`.cdfd` 文件把一个图保存为 `componentList` 和 `connectionList`。导入器将这些 XML 元素映射到 JSON 使用的同一个内部 CDFD project 模型。因此，算法只面向一个公共模型工作，而不是面向多套互不相关的输入格式。

YAML 和 CSV 不作为 CDFD 输入格式。YAML 只是为同一 JSON 契约提供另一种语法；CSV 无法完整表示 module、process 端口、分解、控制条件和 CDFD 结构。

### 2.3 路径定义

**定义 4（process port）。**
对于 process `p`，输入端口 `q_in` 是一组输入数据项或输入边；输出端口 `q_out` 是一组输出数据项或输出边。同一输入端口内使用 AND 语义。不同输入端口默认互斥，除非 CDFD 显式说明。不同输出端口默认也是备选关系；同一个被选中输出端口内的多条边可以共同产生。

**定义 5（port readiness）。**
令 `D` 为可用数据项集合，`A` 为已激活上游节点集合。process `p` 的输入端口 `q` 就绪，当且仅当分配给 `q` 的每条非控制输入边都满足数据可用且源节点已激活：

```text
Ready(p, q, D, A) 当且仅当
对所有 e in InEdges(p, q):
data(e) subseteq D 且 src(e) in A
```

如果端口声明 `mode = any`，则一个输入项就绪即可。默认模式是 `all`。

**定义 6（process activation）。**
当至少一个输入端口就绪时，process `p` 可以被激活：

```text
Fire(p, D, A) 当且仅当
存在 q in Pi_in_p，使 Ready(p, q, D, A) 成立
```

如果没有显式端口，则 process 的输入列表被视为一个 AND 端口。

**定义 7（atomic path）。**
原子路径是 source-to-sink 数据流轨迹：

```text
pi = <v0, e1, v1, ..., en, vn>
```

其中，`v0 in Vs`，`vn in Vt`，`src(ei)=v(i-1)`，`dst(ei)=vi`，每条 `ei` 都可遍历，并且路径中每次 process 激活都满足定义 6。

**定义 8（concurrent path）。**
并发路径是结构化路径项：

```text
C ::= v | C1 ; C2 | Par(C1, ..., Ck) | Xor(C1, ..., Ck)
```

顺序组合显示为 `->`，并行组合显示为 `[A || B]`，互斥备选通过路径关系显示为 `XOR`。合法并发路径必须具有合法的原子路径投影，并保持 fork、join 和端口激活约束。

### 2.4 CDFD 解析

JSON 解析器先根据 JSON Schema 验证文件，然后创建 `CDFDProject`、`CDFDGraph`、`Node`、`Edge`、`PortSpec` 和 `GraphStructure` 对象。SOFL 解析器读取 XML 组件，通过组件名和 `shapeIndex` 解析端点；当可见线实际接触组件但 XML 端点缺失时，退回到基于坐标的端点推断；并保留布局、端口数量、connector index 和边类型作为 metadata。

解析完成后，JSON 和 SOFL 输入都表示为同一图模型：

```text
Input -> CDFDProject -> Path Algorithms
```

### 2.5 合法性与一致性检查

工具执行两层验证。Schema validation 是硬检查：如果 JSON 结构不符合约定格式，文件会被拒绝。CDFD consistency check 是警告，因为早期 CDFD 模型可能不完整。当前检查包括：

- process 节点缺少 process specification；
- process specification 没有被任何图节点使用；
- 图中的数据流没有在 module 变量中声明；
- process 输入/输出声明与图中数据流或端口不一致；
- data store 断连；
- decom 引用缺失图层；
- 环结构会单独报告，而不是直接作为错误。

### 2.6 系统功能

当前系统提供以下用户功能：

- 导入标准 JSON 和 SOFL `.cdfd` 文件；
- 自动推断或显式接受 start/end 节点；
- 生成原子 source-to-sink 路径；
- 生成结构化并发路径；
- 分析 parallel、exclusive 和 joined-output 等路径关系；
- 对原子路径执行多层 process 分解展开；
- 渲染 SOFL 风格 SVG 图；
- 提供 Web UI、Web API 和 CLI 输出；
- 导出 text、JSON、CSV 和 Markdown 结果。

## 3. 关键技术细节

本节说明模型设计，以及不同 CDFD 情况下使用的算法。

### 3.1 模型设计

公共模型把图事实与算法结果分开。`Node` 和 `Edge` 保存导入的 CDFD；`ProcessSpec` 和 `PortSpec` 保存 process 接口；`GraphStructure` 保存 explicit parallel、choice 等 CDFD 结构；`PathResult` 保存一条原子路径，包括节点、边 id、边源点、边目标点、边数据、输出数据、前置条件和控制条件；`ConcurrentPathResult` 保存由 `node`、`sequential` 和 `parallel` 元素组成的树，并提供用于导出的扁平摘要。

该设计是保守的。如果 process 有多个输出端口且没有显式 parallel/fork 结构，算法会把不同端口视为备选。如果几条输出边被分配到同一个输出端口，则它们可以由同一个被选中端口共同产生。

### 3.2 原子路径算法

原子路径生成器在可遍历数据流边上执行深度优先搜索。每一步都会更新可用数据、已激活节点和收集到的条件。只有当目标 process 在当前数据和端口状态下可以激活时，候选边才被接受。

生成器支持两种环处理策略。默认 `simple` 策略禁止同一路径中重复节点，因此有限节点集保证终止。`max-depth` 策略允许重复节点，但受用户给定深度限制。全局 `max_paths` 限制用于避免组合爆炸。

### 3.3 并行分叉

当一个节点有多条输出分支时，算法需要判断这些分支是备选还是并发。显式 `parallel`、`broadcast`、`fork` 或 `separate` 结构表示并发分支。显式 `choice`、`condition`、`select` 或 `non-determinism` 结构表示备选。不带显式结构时，来自不同输出端口的分支视为备选；来自同一个被选中输出端口且条件不冲突的分支，可以组成并发分支。

### 3.4 Join 与同步多输入

Join 行为由 token search 处理。一个 token 可能在所需输入尚未全部可用时到达某个 process。在这种情况下，算法记录已到达数据，但延迟激活 join 目标。只有当目标所需输入端口就绪后，该目标才会被激活。这支持两个分支都完成后，下游 process 才能运行的情况。

对于同步多起点图，初始状态可以包含多个 token，例如一个外部输入 token 和一个 data-store token。生成的并发记法可以显示为：

```text
[IN || STORE] -> Process -> OUT
```

### 3.5 互斥端口

多个输入端口被视为备选。例如，登录 process 可以接受 password 端口 `{userAccount, passWord}` 或 token 端口 `{token}`。只有 `passWord` 时 password 端口不能触发，因为该端口需要两个数据项；token 端口则可以独立触发。因此，同一个 process 节点也可能根据被激活端口不同产生不同合法路径。

多个输出端口默认也是备选。这可以防止工具错误地把 process 的所有输出边都当作同时输出。并行输出必须通过共享的被选中输出端口或显式 CDFD parallel/fork 结构表示。

### 3.6 多层 Process 分解

Process specification 可以包含 `decom` 字段，指向低层图。在原子路径生成中，多层模块会用分解图路径替换该 process，并把父图边连接到子图输入和输出。当前实现支持跨多个图层的稳定原子展开。跨嵌套分解图的统一并发展开仍是限制。

### 3.7 可视化与输出

SVG 渲染器使用 SOFL 风格 process 框、data-store 框、condition 菱形、实线数据流箭头、虚线控制流箭头，并在可用时使用导入布局坐标。没有布局信息的 JSON 图会自动排版。Web UI 聚焦导入图、生成路径、并发路径、路径关系和一致性警告。CLI 提供同一套分析，方便可复现实验。

## 4. 案例分析

下表总结测试和演示中使用的代表性示例。

| 输入 | 主要 CDFD 特性 | 生成结果 | 含义 |
| --- | --- | --- | --- |
| `cdfd_v1.json` | process A 后分叉 | 两条原子路径；B 和 C 被报告为并行分支。当前记法包含 `IN -> A -> [B || C] -> OUT_X4 -> OUT_X5`。 | 工具识别出 A 后的独立分支；多个 sink 节点的终点记法仍较保守。 |
| `join.json` | fork 后 join | 两条原子路径和一条并发路径：`IN -> Split -> [L || R] -> Combine -> OUT`。 | Combine 只有在 `l_done` 和 `r_done` 都可用后才激活。 |
| `data_store.json` | 同步多输入 | 并发记法：`[IN || PROFILE_STORE] -> BuildResponse -> OUT`。 | 外部请求数据和已存 profile 数据都需要就绪，response process 才能运行。 |
| `multilevel.json` | process 分解 | 跨四个图层的三条展开原子路径。 | A1、A3 和 A33 被替换为低层 CDFD；状态/控制节点 s1 和 s2 成为路径条件。 |
| `port_alternatives.json` | 互斥输入端口 | 两条合法路径：一条通过 token 端口，一条通过 password 端口。 | password 端口需要 `userAccount` 与 `passWord`；只有 `passWord` 不能激活 Login。 |
| `xuexitong.cdfd` | 真实 SOFL `.cdfd` 导入 | 四条原子路径和一个 exclusive 路径关系。 | 导入器保留 SOFL 图中的 process、data store、condition、control-flow 和布局信息。 |
| `loop.json` | 含环 CDFD 结构 | simple 模式避免重复节点；max-depth 模式允许有界环探索。 | 终止性由路径策略、深度上限和路径数量上限控制。 |

`join.json` 的输出展示了目标并发路径记法：

```text
IN -> Split -> [L || R] -> Combine -> OUT
```

这条结构化路径对应两个合法原子投影：一个经过 `L`，一个经过 `R`。Join process 不能由任意单个投影单独激活；它需要两个分支输出都可用。

## 5. 不确定点与限制

有两点尚未完全确定，需要明确写出。

第一，SOFL `.cdfd` 文件以工具特定方式保存 connector 和坐标信息。导入器会保留 connector index 并推断缺失端点，但仍需要更多真实 SOFL 文件验证所有端口映射情况。

第二，多层原子路径展开已经实现，但跨嵌套分解图的统一并发展开尚未完成。后续版本应在子图含并发结构时，将被分解 process 替换为并发子树。

## 6. 结论

本文提出了一个 CDFD 路径生成方法和工具，覆盖任务要求：定义完整输入格式，将 CDFD 数据解析为公共图模型，检查合法性与一致性，生成原子路径和并发路径，处理 process 端口与不同算法情况，并可视化结果。核心思想是把 CDFD 路径生成视为语义图问题。原子路径捕捉 source-to-sink 数据流轨迹，并发路径捕捉独立分支与同步 join。端口感知规则避免了常见错误：把多端口 process 误当成所有接口同时激活。实现和案例分析表明，该方法能够支持 JSON 输入、SOFL `.cdfd` 导入、多层示例、端口备选、join 和含环图。
