# 2.4 长计算、滚动、切幕与上下文承接 — 开发交付

**2026-10-30｜独立分支 feature/animation-engine-v1-step2-4**

> 用户明确指示先开发、不要运行测试。本轮所有代码均为待验收实现，不能把接口已经编写宣传为视觉效果已经通过。暂不建立可能触发自动 CI 的 PR，不合并 main。

## 职责与完整性

- 输入严格为已批准的 StoryboardPlan v1.0 与 ExecutionPlan v1.0；每次生成计划前重放执行合同并逐字段比对。
- 数学内容、对象 ID、来源步骤、原 LaTeX 和口播语义锚点始终来自教师模块。动画层只处理显示、保留、滚动、归档和换幕；不填补缺失数学步骤，不制造没有说出的字幕。
- 固定层：原题题干、显式批准的结论或条件；工作层：当前完整计算步骤；历史层：此前确实已经展示、可以滚走或移出本幕的公式。
- 一次教学事件不可从中间割裂：先决定其全部可见内容是否容纳，再决定写入、局部上移或换幕。
- 固定题干的中文使用 CJK 字体，题干及板书数学采用 Manim MathTex；无答案框、无假 TeX、无假秒级语音时间轴。

## 本次编写的模块（尚未运行）

- animation_engine/src/animation_engine/longboard_plan.py — 长板书决策层。提供 LongboardPolicy / build_longboard_plan，逐事件计算实际字形大小、像素位置、固定层、显示性归档、上移、切幕、跨幕承接及稳定来源哈希。无法安全放入完整步骤时显式报告 PAGE_UNFIT / LONG_FORMULA_UNFIT，不裁切。
- animation_engine/src/animation_engine/longboard_render.py — 全程单个 Manim Scene 逐事件真正写入、持有、位移、淡出历史内容与切幕；高亮仅作用于确实可见的对象，并恢复墨色。经 FFmpeg 将固定题干与实际视频逐帧合成，输出 MP4 + manifest。
- animation_engine/src/animation_engine/longboard_header.py — 独立、固定、可核验的中文/MathTex 透明题干叠层。保守拒绝未支持的复杂混排，绝不偷偷修改原题。
- animation_engine/src/animation_engine/cli.py — 新增 plan-longboard / render-longboard 两个 CLI 子命令，不替换既有 2.1—2.3 接口。
- animation_engine/examples/longboard_policy.template.json — 可核验的对象保留、事件切幕与安全分行配置模板。

## 策略

首先尝试在完整工作区继续书写；空间不足时，若只需少量位移，就在事件边界将不再显示的旧过程归档并上移剩余对象；累计滚动过多或需要迁移过远时换幕。新幕保留显式固定结果与最近的必要上下文，并完整显示当前事件的新公式。

已完成的数学对象只能使用原 object_id 和原 LaTeX 原样承接，不得重复以 Write 宣称为新计算；历史已写公式通过保留、移动或恢复呈现。原教师模块明确 remove 的对象不能被固定策略复活。视觉导演因条数限制自动归档、但此前已真正出现且用户明确标记为重要的结果，可以显示层持续保留。

长公式允许在顶层加减号等真实数学结构边界拆为完整可渲染片段；所有片段拼接必须逐字符还原原文，分式内部、根号内部、矩阵内部和 TeX 环境绝不拆断。更复杂的格式应由教师给出已审核 break_hints。原式本身无法安全处理时必须报错，由上游修订，不将布局失败伪装为正确视频。缩放下限为原字号的 90%。

pinned_ids / result_ids 用于标注教师批准的固定结果与条件。它们必须来自原执行合同；不靠数学含义猜测。cut_before_events 可明确指定合法事件边界。全片语义节奏为 preview_only_not_audio_aligned，尚未接入 TTS 或生成实际字幕。

## 以后验收时的命令（本次没有执行）

首先沿用现有命令生成 storyboard.json 和 execution.json。

规划完整长板书：

    math-animation plan-longboard --storyboard storyboard.json --execution execution.json --policy animation_engine/examples/longboard_policy.template.json --output longboard.json

渲染整段视频：

    math-animation render-longboard --storyboard storyboard.json --execution execution.json --policy animation_engine/examples/longboard_policy.template.json --output lesson.mp4 --manifest lesson.json --fps 30

需要 Manim 0.22.1、latex、dvisvgm、FFmpeg 和中文字体。只能处理离线受控教学数据，部署公网服务前还必须隔离 TeX 进程并限制 CPU、内存及运行时间。

## 尚未验收与明确限制

本轮没有运行任何脚本、测试命令或视觉渲染，没有生成新的题目或答案，也没有验证所编写的代码实际执行成功。未来需要检查 Python 代码与真实 Manim/FFmpeg 的兼容性、状态一致性、所有已出现公式不被跳过、局部滚动与换幕是否视觉自然、长公式与复杂题干是否真正可容纳。

几何标签和图形的专项跨幕视觉布局，以及复杂矩阵对照属于 2.5 深化内容；任何一个需要这些高级能力的真实题目，如当前版不能安全显示，就明确拒绝，不能做假验收。

## 下一次验收（用户再授权后）

独立创造一题含明确分项计算和完整推导的考研数学题及参考答案，并由数学教师模块审核每个必要计算步骤。先检查题目和计算正确性，再从头生成教学包、分镜与执行清单，进行长板书计划和全程 MP4 渲染。必须真实看到局部滚动、至少一次换幕、重要结果跨幕继承、逐项计算与最终合并；使用 FFprobe 与实际关键帧验证 30 FPS、无重叠、无裁剪、无漏公式，并回归旧阶段。

**本次仅完成实现代码与说明，未测试、未开 PR、未合并。**
