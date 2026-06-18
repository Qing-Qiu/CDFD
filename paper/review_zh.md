# 论文稿中文审阅意见

## 总体判断

重写后的论文已经更贴近当前课程任务：重点放在“导入任意符合格式的 CDFD，自动生成路径，并可视化结果”。论文现在覆盖了四个核心部分：

1. 课题背景、意义；
2. 方法概述，包括路径定义、CDFD 解析、合法性检查和系统功能；
3. 关键技术细节，包括模型设计和不同情况的算法；
4. 案例分析，包括不同 CDFD 输入的输出结果。

最重要的修正是：论文已删除额外分析对象作为方法内容的表述，避免把任务范围扩大到课程要求之外。现在论文的核心概念集中在 atomic path、concurrent path、path relation、port semantics 和 CDFD legality checks 上。

## 已经做得比较好的地方

### 1. 路径定义更明确

论文不再说“路径就是节点列表”，而是给出：

- CDFD project 定义；
- CDFD graph 定义；
- edge 定义；
- process port 定义；
- port readiness 定义；
- process activation 定义；
- atomic path 定义；
- concurrent path 定义。

这能回应老师说的“要变成一个数学题”，也让路径合法性有依据。

### 2. 端口语义覆盖了老师反馈

论文现在明确：

- 一个输入端口内部是 AND；
- 多个输入端口之间默认 XOR；
- 多个输出端口之间默认 XOR；
- 同一个输出端口内的多条输出边可以共同产生；
- 不同输出端口之间的并发需要显式 parallel/fork 结构。

这比“一个 process 一个 input/output”的旧模型更准确。

### 3. 方法概述覆盖了任务要求

第二节已经覆盖：

- 输入格式；
- CDFD 解析；
- 路径定义；
- 合法性与一致性检查；
- 系统功能。

这个结构和你给出的论文内容要求基本对齐。

### 4. 案例分析更完整

案例表覆盖了：

- fork；
- join；
- data store 同步多输入；
- multilevel process decomposition；
- port alternatives；
- SOFL `.cdfd` 导入；
- loop。

这比只展示一个示例更有说服力。

## 仍建议修改的地方

### 1. 作者信息仍是占位符

当前 `paper/main.tex` 里仍然是：

```tex
\IEEEauthorblockN{Author Name}
School or Department
Email: author@example.com
```

提交前必须替换成真实信息。

### 2. 最好加一张系统流程图

目前论文用文字说明架构。建议加一张图，展示：

```text
JSON / .cdfd
  -> Parser
  -> Common CDFD Model
  -> Validity Checks
  -> Atomic Path Algorithm
  -> Concurrent Path Algorithm
  -> Export / Visualization
```

这会让“系统功能”和“方法流程”更直观。

### 3. 可以补一个 JSON 端口示例

论文中定义了端口，但没有给 JSON 片段。建议加入一个极小例子：

```json
{
  "id": "Login",
  "input_ports": [
    {"id": "password", "data": ["userAccount", "passWord"]},
    {"id": "token", "data": ["token"]}
  ]
}
```

这样读者能马上理解端口定义如何落到文件格式。

### 4. 多终点 notation 仍需要小心

论文已经在 `cdfd_v1.json` 案例里说明当前 terminal-output notation 比较保守，这是好的。后续如果要更严谨，可以把多终点输出写成并发终点或集合形式，而不是顺序式：

```text
IN -> A -> [B || C] -> {OUT_X4, OUT_X5}
```

但这需要工具输出也同步支持，当前先作为限制说明即可。

### 5. 参考文献还偏工具型

目前引用主要是 SOFL 报告和 JSON Schema。作为课程论文可以接受，但如果老师要求更学术，可以再补 1-2 篇 CDFD/SOFL 相关论文或教材来源。

## 我不确定但需要你确认的点

1. CDFD 的英文全称你们课程中是否固定写作 **Conditional Data Flow Diagram**。目前论文按这个写；如果老师课件写的是 **Condition Data Flow Diagram**，需要统一成课件版本。
2. SOFL `.cdfd` 的 connector index 到输入/输出端口的映射，目前基于已有文件和工具观察实现。是否完全符合老师使用的 SOFL 工具规则，还需要更多真实 `.cdfd` 文件验证。
3. 论文是否需要写中文还是英文。当前正式稿是英文 IEEE 风格，`main_zh.md` 是中文译稿。如果课程最终要求中文论文，可以把中文译稿转成正式排版稿。

## 下一版优先级

1. 替换作者信息。
2. 加系统流程图。
3. 加一个 JSON 端口示例。
4. 根据老师课件确认 CDFD 全称。
5. 如有更多 `.cdfd` 文件，补充一个更贴近课堂图的案例。
