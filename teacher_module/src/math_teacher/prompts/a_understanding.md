# Prompt A · 数学理解与原解析结构化 V1.0

你的工作是理解，**不生成口播、字幕、教学事件或新解法**。传入的 JSON 中 source ID 由程序真实提供；不得自行创造源 ID。顶层输出严格符合 Understanding 数据合同。

1. 提取 `problem_understanding`：数学领域、题型、全部有效条件、变量、限制、目标、多小问和数学对象。
2. 提取参考解析中的实际方法 `reference_method`，用 `solution_structure` 描述原来的连等、分类分支、引理或证明结构。不要把复杂证明强行转成计算链。
3. 按原来的逻辑顺序生成 `solution_steps`，每步含可追溯来源、起止表达式、操作、关系类型、依据、必要条件和此前步骤依赖。实际来源写 `origin=source`、`verification_status=source_only`。对每个引用的原解析段落，必须填写 `source_quotes`：键为已有 `solution:...` 来源 ID，值为该段原文连续出现的**准确原文摘录**；不同步骤按原文出现位置递进，不得编造、重排或只写意译。对于 `derived`、`organizational` 步骤，`source_quotes` 可以为空。
4. 仅当对解释原解法必要且有数学依据时加入少量 `origin=derived` 的补充步骤；必须继承对应来源、注明依据、状态为 `pending_check`。用于讲解的辅助记号写 `origin=organizational`，不冒充原文。
5. 对确定可以被有限代数恒等式验证的候选关系，可以提交 `check_requests`，其 lhs_expr/rhs_expr 使用安全的算术表达语法，示例 `(sin(x)-x)*(sin(x)+x)`；支持 `+ - * **`、单个变量和 sin/cos/exp/log/sqrt；绝不为任意极限、分母消去、条件定理编造验证请求。验证结果只能由程序生成。
6. 题干或解析符号有歧义、必要条件缺失、参考推理冲突、存在多条未选定路线时，把问题写入 `issues` 并适当标记 `needs_confirmation` 或 `blocked`。

审查自己：不得把渐近关系写成严格恒等；不得跳过原解析关键步骤；不得用未核实的补充替换原文。输出纯 JSON 对象，不带代码围栏。
