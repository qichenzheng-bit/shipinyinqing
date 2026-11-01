# 视觉导演模块 V1.0（纯离线视觉计划）

本模块只根据数学教师 `TeachingPackage` **生成可复现、可检查的 `StoryboardPlan`**，不调用真实 AI，也**不生成** Manim 场景、动画视频、TTS 音频或音视频时间轴。本模块不修改数学教师代码。

## 已实现

- 白色电子白板主题、顶部固定题干（普通题干居中；长题多行左对齐）、独立字幕安全区。结果不自动加框。
- 教学事件按顺序组织为 `full_board`、`split_scratch`、`matrix_compare`、`proof_scroll`、`diagram_split` 五种**布局策略**（不是固定题型模板）。
- 每个视觉动作保留原始 `board_action_id`、数学对象 ID、LaTeX 原文、原解析步骤 ID 和 `speech_unit_id`；不猜测动画秒数。
- 数学知识点/本题应用临时使用旁侧草稿区；回归普通推导时归档临时公式，保留可追溯记录。
- 长讲解保留最近的公式，旧内容归档，支持后续引用重新恢复；不会删除已讲数学内容的来源记录。
- 矩阵前后结果在容量允许时保留比较；无法保证子表达式对应的数学变形一律安全降级为逐步书写，不假装计算动画正确。
- 图形是**按需显式配置**：只有提供点、线、曲线的 `DiagramSpec` 才出现图形；对其标签做保守的几何避让，无法安全放置则阻断，不强制任何题目配图。
- 字幕严格来自教师 `subtitle.parts`，逐项核对口播语义源中的文字/数学片段。字幕中的公式保留 LaTeX，`reading_intent` 不复制到字幕；口播和字幕不混用。
- 严格来源与 ID 关联验证；被数学教师阻断的包禁止转换。`needs_review` 只能显式开启并保留警告。

## 安装与运行

Python 3.10+：

```bash
cd visual_director
python -m pip install -e '.[test]'
python -m pytest -q

# 已提供真实题目 + 模拟教师输出的教学包（不需要 API）
visual-director plan examples/limit_teaching_package.json --output output/limit_storyboard.json
visual-director schema --output output/storyboard.schema.json
```

也可以运行 `PYTHONPATH=src python -m visual_director plan ...`。

手工提供图形数据可使用 `--options examples/diagram_options.json`（图形 `event_id` 必须出现在教师教学事件中；示例只是结构与布局演示，**不是从题目自动推导的数学图形**）。

输出字段：`theme`、`header`、`scenes[].layout / regions / actions / visible_ids / archived_ids / object_regions / diagram`、`captions`、`warnings`。坐标是归一化区域，不是最终像素/实际动画时间。

## 质量与边界

- 默认题目顶部居中；超长题干需要独立的排版验证，无法容纳时明确报 `HEADER_OVERFLOW`，不会无限缩小字体。
- 归档并不意味着省略推导：以前的教学事件和板书动作仍可追溯。视觉实现后必须确保滚动/归档与实际语音顺序一致。
- **无真实音频**，不能声明口播与板书已精确到秒；`speech_unit_id` 仅是语义锚点。
- **无真实 LaTeX 字体测量与 Manim 渲染**。当前仅检查区域边界、字符串级公式长度与图形坐标的保守碰撞；实际字幕换行、公式尺寸、可视元素重叠需在渲染模块二次验收。
- 从教师 V1.0 缺失数学子表达式映射的情况下，无法自动产出可信的数学局部变形动画；安全降级而非乱匹配。
- 图形点、线、曲线的数学上必要相交允许；不允许标签遮挡无关图元。图形坐标需从可靠的题目几何数据传入，不允许视觉导演凭空编造。
- 本版只做离线程序和约束验证；教学质量与真实视频流畅度仍待后续引擎及真人验收。

## 不开发的范围

真实 AI 集成、教师推理与参考解法修改、语音/朗读、字幕实际时间轴、Manim 动画代码、视频渲染、前后端、V2 兼容代码。
## V1.0 审查修复（2026-10-29）

- 验证 `TeachingPackage.input_sha256` 与原始来源数据的一致性；`StoryboardPlan.source_package_sha256` 另记录完整教学包的确定性指纹，防止仅修改板书而缓存仍误用同一来源版本。
- `retain` / `group` 不再把未写出的对象直接变成可见；历史对象的恢复产生显式 `restore` 动作，容量滚动和临时草稿退场产生 `archive` 动作。
- 字幕要求每个语音单元恰好对应一条字幕候选且顺序一致；仍不添加伪造的音频秒数。
- 几何标签避让使用完整线段与矩形碰撞判断，替代可能漏检的九点抽样。
- 真实 MathTex 字形包围盒与像素级碰撞只能在未来的 Manim/布局模块验证；当前离线分镜不会虚构已完成该项验收。

### 二轮定点修复：教师合同与板书生命周期（2026-10-30）

- 接受确定性、与 JSON 属性排序无关的新来源哈希，并兼容原 V1 示例字段顺序的旧哈希。
- 新教学包携带 `validated_content_sha256` 时校验完整内容摘要，不允许无声修改板书后继续使用旧摘要；旧版没有摘要的示例仍可用于离线规划，但标记 `LEGACY_UNSEALED_PACKAGE`，不能视为新的教师端验证结果。
- 高亮归档对象先显式 `restore` 再 `brief_highlight`，避免未来引擎发生突然跳出的板书。
- 极限题示例中的原解析步骤已补齐逐字来源摘录，与教师 V1.0 新增的 `source_quotes` 约束保持一致。
