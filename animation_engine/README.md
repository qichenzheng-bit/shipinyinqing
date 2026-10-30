# 数学动画执行模块 V1.0 — 第 1 阶段：执行接口与对象状态管理

**当前只输出执行清单 JSON，不生成 Manim 动画、图片、MP4、真实字幕秒数或配音。**

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
