# 面向 Conditional Data Flow Diagram 的端口感知并发路径生成器

作者姓名  
课程项目  
学院或系别  
邮箱：author@example.com

## 摘要

Conditional Data Flow Diagram（CDFD）适合描述以数据为中心的软件规格说明，但从 CDFD 中生成路径并不只是普通图遍历问题。一个 process 可能具有多个输入端口和输出端口，一次执行中通常只有一个端口被激活，而互不依赖的分支又可能并发执行。本文提出一个 CDFD 路径生成工具的设计：它接收完整的项目文件，将其转换为公共图模型，检查结构一致性，并生成原子线性路径与结构化并发路径。本文的主要贡献是给出一个一般性的路径定义，明确区分原子路径、并发路径和功能场景；同时提出端口感知算法，支持同一端口内输入的 AND 语义、多个端口之间的 XOR 选择、显式并行结构、汇合、process 分解以及 SOFL `.cdfd` 导入。案例分析展示了工具如何处理分叉、汇合、同步多输入、多层分解以及互斥 process 接口。

关键词：CDFD，SOFL，路径生成，并发路径，图分析，端口语义

## 1. 引言

Conditional Data Flow Diagram（CDFD）用于 SOFL 风格的规格说明中，建模数据项如何被 process 产生、消费、选择和转换。CDFD 接近有向图，但并不等同于普通图：边可以携带数据或控制条件，process 可以分解为低层 CDFD，process 的图形接口也可能包含多个输入端口和输出端口。

因此，本项目目标可以表述为：给定任意满足文档化输入格式的 CDFD 项目，自动生成它的路径，并同时可视化 CDFD 与生成出的路径信息。输入文件必须包含工具所需的全部信息，包括 module 声明、process 规格、图层、节点、边、控制条件、分解关系以及端口级接口信息。

在开发过程中，一个关键需求变得很清楚：路径不能只定义为节点序列。这样的定义无法描述 CDFD 中两个重要情况。第一，两条分支可能相互独立，此时应表示为并发关系，而不是两条互不相关的路径。第二，一个 process 可能有多个输入端口或输出端口。同一端口内的输入是合取关系，不同端口之间则是备选关系。因此，激活一个 process 节点并不意味着它的所有端口都被激活。

本文总结了当前工具的设计与实现。第二节总结需求；第三节定义 CDFD 模型与路径语义；第四节描述实现；第五节给出代表性案例；第六节讨论局限与未来工作。

### 1.1 意义

本项目的意义有两方面。从建模角度看，它澄清了在存在 process 端口、控制条件和并发时，CDFD 路径到底意味着什么。从工具角度看，它提供了一种可重复的方法：解析 CDFD 项目文件，自动获得路径、关系、场景和可视化结果。这使基于 CDFD 的审阅不再完全依赖人工读图，并减少课程报告或规格检查中的歧义。

## 2. 需求与范围

修订后的需求可以概括为四项任务。

### 2.1 完整的 CDFD 输入格式

主要交换格式是 JSON。一个 JSON 项目包含 `module`、`processes` 和 `graphs`。每个 graph 包含节点、边、起点、终点，以及可选的显式结构，如 `parallel`、`choice` 和 `join`。解析器也接受 SOFL 桌面工具的 `.cdfd` XML 文件，并将其映射到同一个内部模型。YAML 和 CSV 不作为 CDFD 输入，因为 YAML 只是重复 JSON 的契约，而 CSV 无法完整表达层次结构、process 端口和结构语义。

### 2.2 图转换与验证

工具使用 JSON Schema 验证 JSON 文件，解析 SOFL XML 的 component list 和 connection list，并构建公共的 `CDFDProject` 对象。它还会检查 process specification 与图中数据流之间的一致性，包括未声明数据、缺失 process specification、断连的数据存储，以及无效的分解引用。

### 2.3 带并行性的路径定义

生成器必须输出原子路径，同时也要表达并发。原子路径适合 source-to-sink 检查。当 CDFD 包含 fork/join 结构或同步多输入激活时，需要并发路径。Functional scenario 被视为基于路径和 process specification 构建出的更高层分析结果，而不是路径的替代品。

### 2.4 可视化

Web 界面聚焦于图和路径信息。它展示 SOFL 风格的 process 框、data store、condition 节点、实线数据流箭头、虚线控制流箭头、生成路径、路径关系、并发路径符号，以及交互式高亮。

## 3. 形式化模型

### 3.1 CDFD 项目

一个 CDFD 项目被建模为：

```text
P = (M, S, G, g0)
```

其中，`M` 是 module 声明，`S` 是 process specification 集合，`G` 是命名图层集合，`g0` 是入口图。一个图被表示为：

```text
G = (V, E, Vs, Vt, R)
```

其中，`V` 是节点集合，`E` 是有向边集合，`Vs` 是源节点集合，`Vt` 是汇节点集合，`R` 是显式结构集合。

每条边 `e in E` 都有源点 `src(e)`、目标点 `dst(e)`、类型 `kind(e)` 和数据标签集合 `data(e)`。数据流和 active-flow 边可以被路径遍历。控制流边不是路径段，而是成为路径条件。

### 3.2 Process 端口

一个 process specification 被建模为：

```text
Sp = (Ip, Op, Pi_in_p, Pi_out_p, pre_p, post_p)
```

其中，`Ip` 和 `Op` 是简化的输入/输出声明，`Pi_in_p` 是输入端口列表，`Pi_out_p` 是输出端口列表。每个端口是一组必需的数据项或边标识。

对于输入端口 `q in Pi_in_p`，就绪谓词为：

```text
Ready(p, q, D, A) 当且仅当
对所有 e in InEdges(p, q)，data(e) subseteq D 且 src(e) in A
```

其中，`D` 是可用数据集合，`A` 是已激活的上游节点集合。因此，同一端口内的输入具有 AND 语义。如果一个 process 有多个输入端口，则当某一个端口就绪时，process 即可触发：

```text
Fire(p, D, A) 当且仅当 存在 q in Pi_in_p，使 Ready(p, q, D, A) 成立
```

这给出了端口之间的 XOR 语义。如果 process 没有显式端口列表，则 `inputs` 被视为一个 AND 组。

输出端口默认也是选择关系。具有多个输出端口的 process 不会自动产生所有端口上的分支。同一个被选中输出端口上的多条边可以共同产生；而不同输出端口之间的同时分支，需要显式 `parallel` 或 `fork` 结构标记。

### 3.3 路径语义

原子路径是一个有向数据流轨迹：

```text
pi = <v0, e1, v1, ..., en, vn>
```

其中，`v0 in Vs`，`vn in Vt`，`src(ei)=v(i-1)`，`dst(ei)=vi`，并且每个被遍历的 process 激活都满足端口就绪规则。

并发路径是一个结构化项：

```text
C ::= v | C1 ; C2 | Par(C1, ..., Ck) | Xor(C1, ..., Ck)
```

工具使用 `->` 表示顺序组合，使用 `[A || B]` 表示并行组合，并通过路径关系中的 `XOR` 表示互斥备选。合法并发路径需要能够线性化为合法原子路径，同时保留 fork、join 和端口激活约束。

### 3.4 Functional Scenario

Functional scenario 是从一条或多条路径派生出的检查对象。它包含输入数据、输出数据、涉及的 process 操作、前置条件、后置条件以及收集到的控制条件。因此，路径描述结构化的数据流可达性，而 functional scenario 描述用于检查的行为上下文。

## 4. 实现

### 4.1 架构

系统包含五层：

1. 输入与解析：JSON Schema 验证和 SOFL `.cdfd` XML 导入。
2. 公共模型：`CDFDProject`、`CDFDGraph`、`Node`、`Edge`、`PortSpec` 和 `GraphStructure`。
3. 图算法：路径搜索、并发 token 搜索、环处理和多层 process 展开。
4. 分析：路径关系、一致性警告和 functional scenario。
5. 展示：CLI 输出、Web API、并发路径导出和 SVG 可视化。

这种分层让算法独立于原始输入来源。JSON 和 `.cdfd` 输入都会在路径生成之前转换到同一个内存图模型。

### 4.2 原子路径搜索

原子搜索是在数据流边上的深度优先遍历。它支持两种环处理策略。默认的 `simple` 策略避免重复节点，而 `max-depth` 策略允许在需要探索环时进行有界遍历。在每个候选转换处，算法更新可用数据、已激活节点、条件和前置条件。如果目标 process 受 process 输入或端口组约束，则只有当激活谓词满足时，转换才会被接受。

### 4.3 并发 Token 搜索

并发搜索维护一个 token 状态：

```text
T = (K, D, A, ET, CT)
```

其中，`K` 是活跃 token 集合，`D` 是可用数据，`A` 是已激活节点，`ET` 是已遍历边，`CT` 是正在构建的结构化 trace。

搜索在以下四种情况下推进 token：

- 显式 fork/parallel 结构创建一个 `parallel` trace 元素；
- 显式 choice 结构或互斥输出端口创建备选路径；
- join 目标只有在所有必需输入可用后才会激活；
- 同步多起点图以一个并行起点元素开始。

结果是一个 `ConcurrentPathResult`，它同时包含树表示，以及节点、边、数据和条件的扁平列表。导出前，并发树会被规范化：展平嵌套的 sequential 节点、删除空分支、合并连续重复的 join 节点。这个步骤可以让导入的 SOFL 图保持可读，因为某些 connection list 可能通过多个分支 token 激活同一个 join 节点。

### 4.4 输出与可视化

工具通过 Web API 和命令行暴露同一套分析结果。JSON 输出包含 `paths`、`concurrent_paths`、`path_relations` 和 `functional_scenarios`。Text 和 Markdown 输出包含单独的并发路径部分，而 CSV 保持为紧凑的原子路径表。SVG 渲染器为 process、data store、condition 节点和控制/数据流边使用类似 SOFL 的符号，使生成图尽量接近原始 CDFD 记法。

### 4.5 SOFL 导入

SOFL `.cdfd` 文件是 XML 文件，其中 `componentList` 存储 process、data store 和 condition 组件，`connectionList` 存储 data、active data 和 control flows。导入器首先通过 `shapeIndex` 和组件名解析端点。如果 XML 把一条可见线存为 outside-to-outside，但坐标实际接触某个组件，导入器会退回到基于坐标的端点推断。Process 端口数量和边的 connector index 会保留为元数据，因此导入的 SOFL 图也可以使用同一套端口感知激活逻辑。

### 4.6 IEEE 与 Overleaf 排版

论文使用 IEEEtran conference 文档类。项目中引用了 IEEE 官方模板页面，本地 class 文件来自 CTAN IEEEtran 包，该包支持 IEEE transactions、journals 和 conferences。源文件可以用 TeX 发行版在本地编译，也可以上传到 Overleaf。在 Overleaf 中，如果平台提供 IEEE Conference Template，也可以把本文内容复制进去。

## 5. 案例分析

下表总结了项目测试和 Web 界面中使用的代表性示例。

| 示例 | 主要特性 | 结果 | 解释 |
| --- | --- | --- | --- |
| `cdfd_v1.json` | process A 之后 fork | 2 条原子路径；并发记法：`IN -> A -> [B || C] -> OUT_X4 -> OUT_X5` | B 和 C 是 A 之后的独立分支。 |
| `join.json` | fork 后 join | 2 条原子路径；并发记法：`IN -> Split -> [L || R] -> Combine -> OUT` | Combine 只有在两个分支结果都可用后才触发。 |
| `data_store.json` | 同步多输入 | 1 条原子路径；并发记法：`[IN || PROFILE_STORE] -> BuildResponse -> OUT` | 请求数据和已存储 profile 数据共同激活 process。 |
| `multilevel.json` | process 分解 | 跨 4 个图层的 3 条展开路径 | A1、A3 和 A33 被展开为低层 CDFD；控制状态 s1 和 s2 成为路径条件。 |
| `port_alternatives.json` | 互斥输入端口 | 2 条合法路径 | Login process 接受 password 端口 `{userAccount, passWord}` 或 token 端口 `{token}`；只有 `passWord` 不合法。 |
| `xuexitong.cdfd` | SOFL 导入 | 4 条原子路径和一个 exclusive 关系 | 导入的 SOFL 图保留了 process、data store、condition 和 control-flow 信息。 |

端口备选案例直接回应了“多个 process 接口不能被折叠成一个通用节点激活”的要求。Token 路径和 password 路径都到达同一个 process，但它们的输入假设不同，必须保持可区分。

## 6. 局限与未来工作

当前实现区分了原子路径、并发路径、路径关系和 functional scenario。它也支持 JSON 端口和 SOFL 端口元数据，并能规范化由 token 汇合产生的常见重复 join 记法。不过仍有两个局限。

第一，多层 CDFD 展开对原子路径是稳定的，但跨嵌套分解图的统一并发展开仍未完全完成。一个被分解的 process 最终应被替换为并发子树，而不只是线性展开路径。

第二，JSON 格式已经支持显式端口，但仍需要更多真实 `.cdfd` 案例验证 SOFL connector index 与 JSON 端口模型之间的映射。

## 7. 结论

本文提出了一个 CDFD 路径生成器，将路径生成视为语义图问题，而不是简单的节点列表枚举。所提出的模型区分原子路径、并发路径和 functional scenario；显式表示 process 输入/输出端口；并使用端口感知激活规则处理 AND 输入、XOR 备选、join 和显式并行。实现提供 JSON 与 SOFL 导入、schema 验证、一致性检查、CLI/API 输出和 SVG 可视化。该设计为从任意 CDFD 项目文件生成路径提供了一般性基础，同时也为多层并发展开和额外 SOFL 端口映射验证留下了明确的未来工作。
