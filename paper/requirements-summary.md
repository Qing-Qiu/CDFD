# CDFD Path Generator 课程论文需求摘要

## 老师反馈的核心问题

1. 路径定义需要从“程序输出的一串节点”提升为一般性的数学定义。
   - 输入不是某一个特殊示例，而是任意满足格式约束的 CDFD。
   - 路径应被定义为可验证的数学对象，例如线性轨迹、并发路径树或偏序结构。
   - 报告里要说明什么是合法路径、路径如何生成、如何处理环和终止条件。

2. CDFD 中的 process 可能有多个输入端口和输出端口。
   - 一个输入端口内部可以要求多个数据同时满足，即 AND 语义。
   - 多个输入端口之间通常是互斥选择，即 XOR 语义。
   - 多个输出端口也不能默认都同时激活；一次 process 激活通常只选择一个输出端口。
   - 同一个输出端口内的多条输出边可表示一次激活共同产生的多个数据。
   - 不同输出端口之间只有显式 `parallel` / `fork` 结构才表示多个分支同时激活。

3. 并行路径需要被明确表达。
   - 普通 path 是 source-to-sink 的原子数据流轨迹。
   - concurrent path 是结构化路径，可表示 `A -> [B || C] -> D`。
   - functional scenario 是路径之上的功能场景分析，不等同于 path。

## 当前项目应该覆盖的任务

1. 设计 CDFD 输入文件格式。
   - 标准格式使用 JSON。
   - JSON 中包含 module、process、process ports、graph layers、nodes、edges、structures。
   - SOFL `.cdfd` 作为导入格式，会转换到同一套内部模型。

2. 将输入转换为图模型。
   - JSON 经过 schema 校验。
   - `.cdfd` 解析 XML 的 componentList 和 connectionList。
   - 所有输入最终转成 `CDFDProject` / `CDFDGraph`。

3. 计算路径。
   - 线性路径：保留 source-to-sink 原子路径。
   - 并发路径：使用 token 状态搜索表达 fork、join、多输入同步。
   - 端口语义：端口内 AND，多端口 XOR，多输出端口默认 XOR。
   - 环处理：简单路径策略和 max-depth 策略。

4. 检查合法性。
   - JSON Schema 格式检查。
   - start/end 自动推断或显式指定。
   - process specification 与图中输入输出的一致性检查。
   - 多层 decom 引用检查。

5. 展示结果。
   - Web UI 展示路径、并发路径、路径关系和 CDFD 图。
   - CLI 输出 text、JSON、CSV、Markdown。
   - SVG 可视化使用 SOFL 风格节点和连线。

## 仍需在论文和后续实现中谨慎说明的边界

1. 多层 CDFD 的并发路径展开尚未完全统一，当前线性多层展开更稳定。
2. JSON 格式已经支持显式端口，但需要更多真实案例验证。
3. 论文中应把 path、concurrent path、functional scenario 三个概念分开写。
