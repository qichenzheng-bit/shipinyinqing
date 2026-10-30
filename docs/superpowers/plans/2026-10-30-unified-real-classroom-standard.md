# 全模块同步的考研数学教学视频课堂标准（已确认）

## 适用范围与分工

**教学内容/Teacher**：确定解题方法、关键依据、不可跳过的推导步骤、知识点/思维引导/易错点/归纳总结的位置与文字；输出可追溯 source_step_ids、MathTex 原式、教学事件。不要为了凑事件而拆过细。长期保持 LaTex 显示、TTS 发音规则、字幕实际口播分离。

**视觉导演/Visual director**：根据教学事件选择版式。简单计算与无需持续可视化图形的题目，优先使用统一 `simple_classroom_policy`，不再为了测试展示功能主动触发切幕/滚动。几何、曲线、多栏、长证明和矩阵型题目可显式选择复杂版式，但必须保留核心的板书教学逻辑。

**动画引擎/Animation**：对每个源事件执行逐式 MathTex Write。未写满时任何已写数学、知识点、解题说明不删除、不移动、不重新排版；下一完整事件放不下才在事件边界执行整板擦除。必要结果可在新板重新写，但只能来自已计算的原始源对象。题干居中且始终保留；解答不加框。若字号/布局不适合则报错，不能挤占底部字幕安全区域或隐藏步骤。

**字体和配色**：数学题干与工作板数学统一 MathTex 字级，正文黑色 `#111111`。思维引导蓝 `#2563EB`、知识点紫 `#7C3AED`、易错点红 `#DC2626`、归纳总结绿 `#0F766E`；类别标题 18px，解释 16px。无强迫分栏或图文重叠。

**音频/字幕**：此阶段没有录制或合成音频，所以不呈现声称实际播出的字幕、不设置虚假精确同步。未来字幕必须取自实际音轨，板书公式始终规范数学写法，TTS 音译和发音映射仅存在语音层。

## 同步实现位置

- 唯一简单题视觉预设：`animation_engine/src/animation_engine/classroom_policy.py`。
- 用户带教学提示的简单题自动入口：`animation_engine/src/animation_engine/cli.py`；显式旧 policy 保持兼容。
- 严格源合同与数学原式：`visual_director` 输出和 `animation_engine/planner.py` 的执行合同；`classroom_cues.py` 校验中文提示和来源步骤；`persistent_chalkboard.py` 执行追加写、真实尺寸/碰撞预检与板满擦除。
- 新题独立教学包：`animation_engine/tools/build_fresh_taylor_classroom.py`；独立符号核验使用 SymPy，不声称直接接入 AI 教师。
- 运行例子：`animation_engine/examples/simple_classroom_policy.template.json`；所有旧模板保留并标记复杂题/历史用途。
- 专项回归：`animation_engine/tests/test_fresh_taylor_classroom.py` + `animation_engine/tests/test_persistent_chalkboard.py` + GitHub Actions 的真实 LaTeX/Manim 视频验收。

## 验收原则

验收不等于只是获得 MP4。必须检查全题数学答案、来源信息、事件数量、每条公式首次书写一次、完整的页内板书延续、擦板仅因页满、跨页必要结果、字体和颜色、题干固定以及视频实际关键帧。

对于本阶段无音频的 demo，采用手工编写且经数学校验的教学包；最终真实教师语音与字幕将作为独立开发能力，不能提前声称已有。