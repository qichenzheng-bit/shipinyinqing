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
