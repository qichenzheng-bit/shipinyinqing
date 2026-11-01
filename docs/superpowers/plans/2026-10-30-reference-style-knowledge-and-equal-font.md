# 课堂视觉校正：公式字级与题干一致、思路与知识点进入黑板

用户对简单题整板模式反馈：当前数学公式仍明显大于题干；此前预留在题干下方的固定讲解栏，并不是参考视频中思维引导、知识点讲解的课堂效果。

## 强制执行的视觉规则

- 题干 MathTex 的字号为 27pt；简单题数学正文使用基础 MathTex 48pt 乘以 0.5625 得到同样 27pt 的字号。只有超宽时允许降至54%（25.92pt），且必须记录并检查，可读性不足时不能继续缩放。
- 删除简单题讲解提示的常驻题干下方提示区。黑板主体中采用阶段性教学：思维引导、知识回顾、观察、检查和总结只在相应事件出现。标题为克制的蓝色正文，不做悬浮大卡片。
- 对应的源 MathTex 公式在知识点标题和文字解释下方逐步写出。实际公式写出后，直接移动同一数学对象进入连续计算区，不复制写入，也不修改原 LaTeX 或数学来源。
- 普通计算与应用事件继续显示实际数学板书，不反复弹出提示。讲解文字保留在教师数据结构内，供未来语音层使用；此版本并未虚构配音或字幕。
- 简单题无须为了展示切幕而切幕，能够完整容纳的真实数学过程就保留在整块黑板中。长题仍可使用原阶段的测量、滚动和切幕。

## 开发修改

- animation_engine/src/animation_engine/longboard_plan.py：显式 `guidance_style=board_context`；允许最低 math_min_scale 0.48 的校验，当前样例为0.54；原 `fixed` 行为保持兼容。
- animation_engine/src/animation_engine/classroom_cues.py：board_context 黑板主体教学段落。教师批准的中文标题、文字、来源步骤和时间仍严格核验。数学由 MathTex 渲染，不由 PIL 伪造。
- animation_engine/src/animation_engine/longboard_render.py：每个相应事件只在黑板中部呈现概念教学，MathTex 于标题下方真实 Write，再移至正式计算布局；中间已有公式临时隐藏并原样恢复，原题不消失。
- animation_engine/tools/build_classroom_rework_example.py：沿用已经审核的14事件分部积分题，改为字号匹配与黑板知识点模式，不改教师解答内容。
- animation_engine/tests/test_classroom_rework.py 和 .github/workflows/classroom-contextual-knowledge.yml：检查输入来源、MathTex 大小、无常驻提示区、旧模式兼容性和真实渲染结果。

## 真实验收

GitHub Actions run #41063168993：离线合同及原动画回归通过，真实 Manim MP4 渲染通过。画面1280×720、30 FPS、约70.77秒，14个教学事件；这道简单题未触发滚动/切幕。manifest 显示7个在主黑板讲解的概念阶段，并记录 Write-with-contextual-guidance 动作。FFprobe、真实视频及各幕图片均在同一 artifact。原题和最终解析值保持不变。

边界：仍是无语音预览，不能声称已经达到真实教师口播和字幕同步；此次是针对学生所见的内容布局、字号和知识点出现方式的专项改造，不等于考研各类题型都完成视觉验收。