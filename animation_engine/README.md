# 数学动画执行模块 V1.0 — 第 1 阶段：执行接口与对象状态管理

**本文的前半部分保留 V1 早期模块历史记录。2.4 长板书、参考视频课堂、持续书写与写满擦板功能现均已有独立真实 MP4 专项验收。简单题已切换为“写上不消失、写满整板擦除”，复杂题保留旧版式。所有当前预览均不等于真实配音字幕同步。**

输入严格使用视觉导演的 `StoryboardPlan v1.0`（Pydantic 原始合同）。输出 `ExecutionPlan v1.0` 包含每场景的动作前后状态、公式所在区域、可见与归档对象、稳定 SHA-256 状态指纹，以及所有来源/口播语义 ID。执行器不改原始 LaTeX、不解题、不进行模型调用。

## 安装

本仓库尚未发布视觉导演到 PyPI，先从源码安装依赖：

```bash
python -m pip install -e './visual_director[test]'
python -m pip install -e './animation_engine[test]'
cd animation_engine && python -m pytest -q
```

## 生成执行清单

```bash
visual-director plan visual_director/examples/limit_teaching_package.json --output storyboard.json
math-animation plan storyboard.json --output execution.json
```

**此时 `execution.json` 不含动画帧、真实时间码。** `sync_status` 是 `semantic_anchors_only`。题干高亮记录为 `question` 区域的动作，**不**将题干公式加入可见板书对象。既有公式 ID 不可偷偷改写 LaTeX 或原始步骤来源。只允许导演已指定的状态变更和区域迁移，每场结束时强制比对 `visible_ids`、`archived_ids` 和 `object_regions`。

## 后续阶段

真实 MathTex/Tex、字体测量、实际 Manim 动画、字幕渲染、几何动画、长证明滚动、音频对齐、分段缓存都属于以后独立验收阶段；不能因本阶段测试通过而宣称已经实现。

## 2.1：真正的 LaTeX 数学静态预览（新功能）

渲染依赖是可选的：基础 `math-animation plan` 不需要 Manim。使用静态预览时安装 `python -m pip install -e './animation_engine[render,test]'`，并在系统中准备可执行的 `latex`、`dvisvgm`、Cairo/Pango 依赖。CI 在 Ubuntu 下安装这些工具并生成**实际 PNG**。

```bash
visual-director plan visual_director/examples/limit_teaching_package.json --output storyboard.json
math-animation plan storyboard.json --output execution.json
math-animation preview-math --storyboard storyboard.json --execution execution.json \
  --event-id <真实场景事件ID> --object-id <在该场景可见的公式ID> \
  --output math.png --metrics math.json
```

注意：这里的 event/object ID 应从 `execution.json` 中实际 `visible_ids` 选取；不能凭空发明。预览会同时验证**整份执行清单**与分镜的一致性、检查对象是否真实可见、按分镜区域预留题干/字幕留白，并通过 Manim MathTex + Cairo 渲染矢量字形到白底 PNG，输出公式实际尺寸、像素坐标、原 LaTeX 和来源步骤。公式太大就报 `FORMULA_OVERFLOW`，不偷缩小、不截断、不用普通文字顶替公式。

**安全边界**：2.1 是离线、受审计教学输入的预览器，不接受公网任意用户提供的 TeX 直接执行。已采取严格数学宏限制，但生产服务仍需独立低权限沙箱、CPU/内存/时间限制及受控缓存。原教师与导演合同不因预览被改写。

**尚未实现**：整幕老师课堂、局部分段书写、短暂蓝色高亮、自动换行/滚动/换幕、中文题干混排、真实音频与字幕秒级同步。这些在后续 2.2—2.5 专项验收。

## 2.2：按数学结构分段写入 + 指定局部高亮（真实 MP4）

新命令 `math-animation render-writing` 在**完整校验** `StoryboardPlan` 与 `ExecutionPlan` 后，对一条已经出现过的数学对象生成**真实的 Manim Write 动画 MP4**。不提供人工审核的分段标记时，只对原式进行整式 Write 和蓝色高亮；若提供标记，则强制片段逐字拼接等于原 LaTeX，且 `source_storyboard_sha256`、`event_id`、`object_id`、原 `action_id` 和 `speech_unit_id` 全部匹配。非法标记报错，不会自行推理或重写数学。

```bash
visual-director plan visual_director/examples/limit_teaching_package.json --output storyboard.json
math-animation plan storyboard.json --output execution.json
math-animation render-writing --storyboard storyboard.json --execution execution.json \
  --event-id e_end --object-id m_end \
  --hint animation_engine/examples/limit_sum_approved_parts.json \
  --output writing.mp4 --manifest writing.json
```

可省略 `--hint` 以试验**安全整式回退模式**。命令行支持 `--pixel-width`、`--pixel-height`、`--fps`，默认 1280×720、15 fps。色彩固定白底 #FFFFFF、墨色 #1E293B、当前高亮 #2563EB，动画只改变颜色，不移动已写好的字符；最终恢复墨色。使用真实 MathTex 生成 MP4 和可追溯 manifest；没有配音，`timing_source=preview_only_not_audio_aligned` 的预览节奏**不是口播对齐时间**。整幕/逐步滚动以及跨多个公式位置跟踪属于后续阶段。

**重要的上游布局限制**：`animation_engine/examples/sin_taylor_approved_parts.json` 可用于验证分段合同，但原视觉导演把该长泰勒式放在较窄的 scratch 区，它按正常字号可能触发 `FORMULA_OVERFLOW`，不是动画失败。2.2 不会擅自缩字/改区域；需要等 2.3 的真实版面重排。故本阶段完整 MP4 验收使用已处于正常 board 区的结论公式 `m_end`。

离线可信输入专用。TeX 编译不能作为无沙箱的公网服务；通过既有宏限制并仍需服务级低权限隔离。禁止把 preview-only 时间当成真实字幕/配音时间。


## 2.4：长计算、自然滚动、切幕与必要板书继承（早期版本，已验收，非当前简单题默认）

2.4 不再受单幕能放下多少公式的限制；从原有完整 StoryboardPlan + ExecutionPlan 生成独立、可追溯的长板书页面计划，逐事件安排固定层、工作层、显示性归档、滚动和切幕。每一幕的数学、对象 ID、步骤来源完全来自教师模块。固定题干持续展示，正常作答不加答案框。允许的移动发生在事件/步骤边界，不打断正在书写的公式。

**本段仅保留 2026-10-30 旧开发阶段的历史说明。2.4 此后已完成独立新题的 MP4 验收；当前简单题不再使用这种频繁重排模式。**

先生成已有的 storyboard.json / execution.json，然后可在将来的验收阶段运行：

    math-animation plan-longboard --storyboard storyboard.json --execution execution.json --policy animation_engine/examples/longboard_policy.template.json --output longboard.json

    math-animation render-longboard --storyboard storyboard.json --execution execution.json --policy animation_engine/examples/longboard_policy.template.json --output lesson.mp4 --manifest lesson.json --fps 30

policy 模板包含 pinned_ids（重要条件）、result_ids（已完成结果）、break_hints（原 LaTeX 严格逐字符重组的合法分行）、cut_before_events（人工批准的事件切幕点）和动态滚动限制。未定义数学语义的对象不可以由动画引擎猜测为答案。默认仅尝试在顶层 + / - 处安全断行；分式、矩阵等不能随意拆散。公式仍不能放下时显式报错，不无限缩小字体，也不偷偷裁切。

- **纯规划**：animation_engine/src/animation_engine/longboard_plan.py
- **真实视频执行**：animation_engine/src/animation_engine/longboard_render.py
- **固定中文/MathTex 题干**：animation_engine/src/animation_engine/longboard_header.py
- **规范和后续验收方案**：docs/superpowers/plans/2026-10-30-animation-engine-step2-4-longboard.md

完整视频会预留语音字幕区域，不伪造字幕时间码；阶段 2.5 再专项处理多题型、几何与矩阵的复杂展示以及视觉回归。2.4 未来验收需要先创造全新题目和经检查的完整参考解答，实测滚动、切幕与结果承接。**没有真实渲染通过之前，不得声称课堂效果已验收。**


## 最新：用户确认的真实课堂持续板书模式（简单计算题）

这不是覆盖原来的 2.3/2.4 代码，而是把默认简单题与复杂题分开。新入口 `classroom_policy.simple_classroom_policy()` 在传入 `--classroom-cues` 且没有显式版式时自动选用 `guidance_style=persistent_chalkboard`。指定旧政策仍走原动画逻辑。视觉导演和执行层不允许为了让公式好看而重写数学内容。

- **原题**：居中且固定、真实 MathTex，数学内容与题干数学字号一致（普通约 27pt），黑色，答案不加框。
- **知识提示**：思维引导、核心知识点、易错点、归纳总结按原定固定字号和不同颜色，属于黑板内容，只在对应数学步骤出现，写完留在画面里。
- **持续书写**：教师事件追加写入；不滚动旧公式、不局部隐藏或淡出、不根据阶段无故切幕。满页时于完整教学事件边界执行一次擦黑板。跨页需要的已得结论依 source ID 重写。
- **排版安全**：实测字形、逐页越界/重叠校验、完整事件不可截断、各块 stable ID 和 math provenance 校验，长公式无法容纳必须显式报错而不是糊弄缩字。
- **未实现项**：完整真实 AI 教师、音频 TTS、字幕按口播同步、几何/矩阵等专项讲解必须独立设计和验收。真实 MP4 不代表成品视频已配音。

### 最新模板及命令

示例教学配置：`animation_engine/examples/simple_classroom_policy.template.json`；标准逻辑唯一入口：`animation_engine/src/animation_engine/classroom_policy.py`。**旧** `longboard_policy.template.json` 仅供多步骤滚动模式使用。

```bash
python animation_engine/tools/build_fresh_taylor_classroom.py --output taylor-demo
math-animation render-longboard --storyboard taylor-demo/storyboard.json \
  --execution taylor-demo/execution.json \
  --classroom-cues taylor-demo/teacher_approved_cues.json \
  --output taylor-demo/lesson.mp4 --manifest taylor-demo/manifest.json --fps 30
```

这是完全新编的考研数学泰勒极限测试，与之前的多项积分和分部积分题不同。构建器生成具有真正数学来源的教学包、分镜和执行计划，CI 使用 SymPy 另行计算极限以核验，随后输出真实 Manim 视频并检验擦板前后关键帧。旧阶段入口和历史测试保留，不进行破坏性替换。


## 教学内容完整性升级：一个教师环节可连续书写多个公式

在分析上一版泰勒极限教学视频后，发现旧版 19 条按公式切分的事件破坏了推导完整性：真正关键的高阶乘法未展开，而简单系数又被独立分段。因此，视觉动画和教育语义必须使用**不同粒度**：

- 教学环节表示一个明确的思维目标，例如“为什么积分因子能使左边合并为乘积导数”；一个环节允许包含多条数学公式。编译器位于 `src/animation_engine/classroom_teaching_units.py`，输入经作者审核的 unit，输出具有合法 `StoryboardPlan` / `ExecutionPlan`、唯一公式 ID 和原始数学步骤来源的事件链。
- 每个教师环节中不同公式仍然逐条 Write，但不会被伪造成多个独立知识点。关键推导需显示中间依据、合并步骤与答案；简单计算不为了增加事件而拆开。单行有实质意义的知识点也允许独立存在，**不以公式数量判断教学价值**。
- 已确认的持续板书模式仍保持“写上就保留，整板写满再擦”；一个完整的教师环节不能在内部被擦板打断。擦板后若确实需要，可按源 ID 重写上一步的关键数学结论，避免不自然的推导断裂。
- `persistent_chalkboard.py` 的布局和真实视频记录含教学环节标题、`math_write_count`、原始步骤集合和擦板原因。检查 4 个教学环节与 11 条数学书写动作是否同源，比检查“成功生成视频”更严格。
- **已修改的旧泰勒题**：`tools/build_fresh_taylor_classroom.py` 从 19 个公式级事件改为 5 个教学环节、12 条完整板书，补上乘法展开五次项的两个来源；已在真实 MathTex 版面上回归。
- **完全新题**：`tools/build_complete_ode_lesson.py` 使用一阶线性微分方程初值问题 `y'+2xy=2x, y(0)=0`，4 个教学环节、11 条初次数学书写。对乘积求导、积分、初值代入与验算连续展开。正确答案 `y=1-e^{-x^2}`，由 SymPy 独立核验。一次写满擦板时把上一板关键结果经原来源重新抄写；没有口播或已同步字幕。

```bash
python animation_engine/tools/build_complete_ode_lesson.py --output ode-demo

math-animation plan-longboard --storyboard ode-demo/storyboard.json \
  --execution ode-demo/execution.json \
  --classroom-cues ode-demo/teacher_approved_cues.json \
  --policy ode-demo/page_policy.json \
  --output ode-demo/board_pages.json

math-animation render-longboard --storyboard ode-demo/storyboard.json \
  --execution ode-demo/execution.json \
  --classroom-cues ode-demo/teacher_approved_cues.json \
  --policy ode-demo/page_policy.json \
  --output ode-demo/lesson.mp4 --manifest ode-demo/manifest.json --fps 30
```

专项验收：`.github/workflows/classroom-complete-units-fresh-ode.yml`。该模型是可信、已审核教学脚本的确定性执行和验证路径，**不自动证明所有解题步骤正确**、不冒充真正教师口播；完整数学真实性仍需要上游内容审核与针对性外部符号核验。
