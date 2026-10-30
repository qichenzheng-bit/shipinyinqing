# 2.5.1：连续计算与分项结果展示（独立开发分支）

**分支**：`feature/animation-engine-v1-step2-5-1`  
**基线**：2.4 提交 `730c711cc310bcf74003f8a1562754deb30c79c3`（2026-10-30，后续 2.4 验收变更不自动进入本分支）。  
**实现边界**：可验证的分项关系 overlay、结果带/总览带、回退、安全渲染复用。此文档不声称已完成真实课堂观感验收。

## 教师教学内容是唯一数学来源

严格沿用既有 `StoryboardPlan v1.0`、`ExecutionPlan v1.0`。分组配置只引用已存在的 `event_id` 和 `object_id`；绝不从 `+` 推断积分是否可拆、从 `I_1` 推断数值结果、改 LaTeX 或编造教师口播。

新增独立的 `CalculationGroupOverlay v1.0`：每个分项具备 `intro_event_id`、有序 `event_ids`、输入/过程/结果对象；归属和合并事件必须由人工或上游教师审核。三个 SHA 绑定完整课程版本，非 `teacher_reviewed` 或 ID、顺序、时间点不合法的 overlay 一律拒绝。分项结果必须在对应分项事件内首次写出，合并必须晚于全部计算。分类讨论、多方法比较不得使用求和合并；依赖链按 2.4 普通长板书处理。

**分项上屏规则**：顶层题干由 2.4 固定中文/MathTex 叠层提供；本阶段只重新安排已被 2.4 核验可见的公式，优先在顶部保留拆项总览，下面保留当前推导，底部安放已经由教师写出的结果。真实尺寸不足时，先释放非必要总览，再恢复原有 2.4 的滚动/切幕。都不能满足则明确失败，不挤字、不裁切、不删除新步骤。最多保留三个已完成结果作为默认选项；更多结果按教师/2.4 可见状态与页面容量处理，不凭空生成缩写摘要。

数学结果如果已经显示，跨页承接使用原对象身份而非重新写出；仅首次合法写入触发 Write。高亮仍只来自原导演动作。2.5.1 不主动制造高亮，也不在未真实配音时合成字幕。

## 运行方式（已生成的原创 2.4 积分题）

```bash
# 先安装 visual_director 和 animation_engine（只规划不需要 Manim）
python -m pip install -e './visual_director[test]' -e './animation_engine[test]'

# 同一原创教学题，完整经过可验证的导演和执行合同
python animation_engine/tools/build_fresh_integral_acceptance.py --output /tmp/calc251

# 用经过明确人工关联的 ID 生成版本绑定的分项 overlay
python animation_engine/tools/build_fresh_integral_group_overlay.py \
  --execution /tmp/calc251/execution.json --output /tmp/calc251/overlay.json

# 纯 JSON 规划：真实 MathTex 测量需要安装 animation_engine[render]
math-animation plan-calculation \
  --storyboard /tmp/calc251/storyboard.json \
  --execution /tmp/calc251/execution.json \
  --overlay /tmp/calc251/overlay.json \
  --policy animation_engine/examples/new_integral_acceptance_policy.json \
  --output /tmp/calc251/calculation_plan.json

# 真视频，需 Manim/LaTeX/dvisvgm/FFmpeg/CJK 字体和 2.4 视频执行能力
math-animation render-calculation \
  --storyboard /tmp/calc251/storyboard.json \
  --execution /tmp/calc251/execution.json \
  --overlay /tmp/calc251/overlay.json \
  --policy animation_engine/examples/new_integral_acceptance_policy.json \
  --output /tmp/calc251/calculation.mp4 \
  --manifest /tmp/calc251/calculation_manifest.json --fps 30
```

`calculation_plan.json` 对每个已批准的原始事件提供 `group_state`：分项阶段、当前项、已完成项、可见总览与结果；并给出 `layout_mode` 和位置变更。原 `source_state_sha256`、`source_storyboard_sha256`、`source_package_sha256`、`speech_unit_id`、`source_step_ids` 始终保留。新 `calculation_plan_sha256` 用于验证布局覆盖层的稳定性。预览标记 `preview_only_not_audio_aligned` 不得解释为已完成口播时间同步。

## 当前验收层级与未实现项

- 契约与布局自动测试：校验来源、数学对象身份、结果时机、分项顺序、总览/结果避让、重复稳定性及多种失败输入。
- 真实成片验收：需 1280×720/30fps 的实际 Manim MP4、关键帧、逐事件 manifest、FFprobe 和人工观感抽查；此项须独立运行，不能由“有渲染入口”替代。
- 暂未完成：复杂矩阵、动态几何、跨多个独立分组的统一混排、真实音频时间轴、逐句字幕/TTS、基于数学证明自动确定分项，以及任意互斥条件的自动求和验证。无可靠关系时请继续使用 2.4 `plan-longboard`/`render-longboard`。

**隔离原则**：不改 2.4 分支、`main` 和教师数学逻辑；不自动合并任何 PR。公网执行 TeX 仍需单独沙箱及计算资源限制。
