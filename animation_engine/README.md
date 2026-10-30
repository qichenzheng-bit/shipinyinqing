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
