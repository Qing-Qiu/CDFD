# 论文稿中文审阅意见

## 总体判断

这篇稿子已经能作为课程论文初稿使用。它抓住了老师反馈的核心问题：路径定义不能只是节点序列，必须考虑并行路径、process 多输入/输出端口，以及 functional scenario 与 path 的概念区分。论文结构也比较完整，覆盖了课题背景、需求、形式化定义、系统实现、案例分析和局限性。

当前最值得保留的亮点有三点：

1. **问题意识明确**：开头直接指出 CDFD 路径生成不是普通图遍历，因为存在控制条件、process 分解、端口和并发。
2. **形式化定义方向正确**：用 atomic path、concurrent path 和 functional scenario 三层概念回应老师对“数学定义”的要求。
3. **工具实现与论文互相支撑**：论文中提到的 JSON schema、SOFL `.cdfd` 导入、端口语义、并发路径和 SVG 可视化，都已经能在代码中找到对应实现。

## 必须修改或补强

### 1. 作者信息仍是占位符

当前 `main.tex` 中仍是：

```tex
\IEEEauthorblockN{Author Name}
School or Department
Email: author@example.com
```

提交论文前必须改成真实姓名、学院/课程信息和邮箱。这个属于格式性硬伤，老师一眼会看到。

### 2. 需要补一张系统流程图或架构图

论文现在文字讲清楚了系统分层，但 IEEE 论文如果只有文字和表格会显得略“报告化”。建议加入一张图，展示：

```text
JSON / .cdfd
  -> Parser
  -> CDFDProject / CDFDGraph
  -> Validation
  -> Atomic path search
  -> Concurrent token search
  -> Export / Web visualization
```

这张图可以对应 README 中已有的架构图，放在 Implementation 开头附近。

### 3. 案例分析还缺少真实输出片段

目前第五节用表格总结案例，信息密度不错，但证据感还可以更强。建议至少加入一个小例子的实际输出，例如：

```text
IN -> Split -> [L || R] -> Combine -> OUT
```

并解释它如何由两条 atomic path 合成 concurrent path。这样能更直接支撑“路径语义表达更清楚”这个贡献点。

### 4. `cdfd_v1.json` 的多终点 notation 需要谨慎描述

表格中写：

```text
IN -> A -> [B || C] -> OUT_X4 -> OUT_X5
```

这个表达读起来像 `OUT_X4` 之后又顺序到 `OUT_X5`，而实际语义更可能是两个终点输出。目前论文在 Limitations 中已经承认“多终点并行 notation 仍可能顺序化”，但案例表格里最好加一句 `current notation` 或换成更保守的描述，避免老师追问。

推荐改法：

```text
2 atomic paths; parallel relation between B and C branches
```

或者：

```text
current notation: IN -> A -> [B || C] -> OUT_X4 -> OUT_X5
```

并在解释中说 terminal-output notation is still a limitation。

### 5. 算法复杂度和终止性可以补一小段

老师提到“定义要变成数学题”，除了定义路径，还应说明算法为什么会停。建议在 Atomic Path Search 或 Concurrent Token Search 后补充：

- `simple` 策略通过禁止重复节点保证有限；
- `max-depth` 策略通过深度上限保证有限；
- `max_paths` 是防止组合爆炸的安全上限；
- 并发 token 搜索用 visited state 去重。

这会显得方法更严谨。

## 建议增强

### 1. 引言里可以更早点出课程任务

现在引言比较学术，但可以加一句更直接的话：

> The course task is to import an arbitrary CDFD project file following our format and automatically output its paths.

这样和老师布置的任务衔接更强。

### 2. JSON 格式部分可以补一个极小示例

第二节说 JSON 包含 module/processes/graphs，但没有示例。可以加一个简短 JSON 片段，展示 `input_ports`：

```json
{
  "id": "Login",
  "input_ports": [
    {"id": "password", "data": ["userAccount", "passWord"]},
    {"id": "token", "data": ["token"]}
  ]
}
```

这能更好解释端口语义。

### 3. SOFL `.cdfd` 导入可以说清楚“不一定先转 JSON 文件”

实现上 `.cdfd` 会被解析进同一个内存模型，不必先落盘成 JSON。论文中已经说 “maps them into the same internal model”，但可以再明确一点，避免读者误会流程是 `.cdfd -> JSON file -> algorithm`。

### 4. Functional scenario 的定位可以再强调一次

论文已经区分了 path 和 functional scenario。建议在案例分析后再补一句：

> The scenario output is not counted as an additional path; it is an inspection view derived from one or more paths.

这能回应你之前强调的 “paths 和 functional scenarios 是不同概念”。

## 语言与格式问题

1. 英文整体清楚，句子没有明显语法硬伤。
2. LaTeX 中有一些代码词使用反引号，例如 `module'、`.cdfd'。这在 LaTeX 中可以编译，但排版效果不如 `\texttt{module}` 稳定。正式稿建议统一改成 `\texttt{...}`。
3. 表格比较宽，使用 `table*` 是合理的；但如果 Overleaf 编译后跨栏位置不理想，可以把案例表拆成两张小表。
4. 本地当前未安装 TeX Live/MiKTeX，所以没有生成 PDF；源文件适合直接上传 Overleaf 编译。

## 建议下一版优先级

1. 替换作者信息。
2. 加系统流程图。
3. 加一个真实输出片段。
4. 补算法终止性/复杂度说明。
5. 调整 `cdfd_v1.json` 的多终点 notation 描述。

完成这五点后，论文会从“能说明项目”变成“更像一篇完整的方法型课程论文”。
