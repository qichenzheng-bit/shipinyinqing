# Animation Engine 2.1 — Real MathTex Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans or superpowers:subagent-driven-development to implement task-by-task. Each task follows RED → GREEN → review.

**Goal:** 从经过校验的 StoryboardPlan + ExecutionPlan 生成真实 MathTex 单公式白底 PNG 预览，记录来源和渲染尺寸；不生成数学内容。
**Architecture:** 纯合同验证 → MathTex 编译与测量 → Cairo 静态 PNG/metadata → 真实 CI smoke，不改变第一阶段的模型。
**Tech Stack:** Python 3.11、Pydantic v2、Manim Community 0.22.1（可选依赖）、LaTeX、dvisvgm、Pillow、pytest、GitHub Actions。
**Spec:** docs/superpowers/specs/2026-10-30-animation-engine-phase2-design.md

## Global Constraints

- 新分支 feature/animation-engine-v1-step2-1，起点 0ca6bd99ae24bacd021f0427c2e2fc550a780781，Draft PR 指向 feature/animation-engine-v1-step1；不合并。
- 颜色白底 #FFFFFF、深灰 #1E293B；蓝色高亮仅 2.2。保留原 LaTeX、ID、step provenance；不创造音轨秒数。
- 真正 MathTex，不用普通文字或渲染失败回退；不缩小塞入溢出区域。
- 仅离线可信数学内容；执行 TeX 前严格输入限制；网络服务需要外部沙箱，不能直接暴露此渲染接口。

## Review Focus

1. execution 被伪造但 storyboard hash 不变：重建整份执行计划后比对，拒绝。
2. 题干 question 高亮不是可见板书对象：明确拒绝。
3. TeX 文件 I/O、重定义命令或不完整定界符：在编译之前失败或有明确 TEX_COMPILE_FAILED。
4. 无 LaTeX 工具链或公式超限：明确 LATEX_ENV_UNAVAILABLE / FORMULA_OVERFLOW，不留下成功 PNG。
5. 云端确认真实像素 PNG、元数据来源、三模块旧测试无回归；不要将 mock 作为渲染验收。

## Task 1: Contract/selection（不需要 Manim）

**Files:** create animation_engine/src/animation_engine/render_contract.py and animation_engine/tests/test_render_contract.py.
**Interfaces:** select_math_render_request(storyboard, execution, *, event_id, object_id) -> MathRenderRequest; RenderContractError.
- [x] 编写可见板书对象/来源保留测试、篡改/错哈希、题干高亮/不存在对象测试。
- [x] 运行 CI RED（run 41000401493；合同接口缺失）。
- [x] 最小实现完整执行计划比对、可见区域选择、稳定来源。
- [x] CI GREEN（run 41000521501）。
- [x] 提交独立 commit。

## Task 2: 真正编译 MathTex 与测量

**Files:** create animation_engine/src/animation_engine/mathtex_renderer.py, animation_engine/tests/test_mathtex_renderer.py; update animation_engine/pyproject.toml optional render dependency.
**Interfaces:** validate_math_latex(latex) -> None; build_measured_mathtex(latex, ink) -> tuple[MathTex, MathGlyphMetrics].
- [x] 写分式、规范下标极限、积分、矩阵真实编译与尺寸测试；危险 TeX、非法表达式、无工具链负例。
- [x] 云 CI 验证 RED（run 41000637510 real-render，模块缺失）。
- [x] 使用 MathTex 真正编译，预编译检查命令与环境，并报告真实几何宽高。
- [ ] 云 CI GREEN 及必要定界符错误修正，复查具体日志。

## Task 3: 单公式 PNG、尺寸/来源 JSON 与 CLI

**Files:** create animation_engine/src/animation_engine/math_preview.py, animation_engine/tests/test_math_preview.py; modify animation_engine/src/animation_engine/cli.py and animation_engine/README.md.
**Interfaces:** render_math_preview(request, *, output_png, output_json, pixel_width=1280, pixel_height=720) -> MathPreviewResult; CLI preview-math.
- [x] 写真实白底 PNG 像素、尺寸/区域、元数据与 CLI、溢出和非法 TeX 负例。
- [x] 云 CI 验证缺失模块和渲染依赖隔离失败（41000775396）。
- [x] 使用 Manim Cairo Camera 输出真实 PNG；若超出 Rect 则失败、不偷缩放；原子化写出产物。
- [ ] 云 CI GREEN，检查真实 PNG 和信息完整性。

## Task 4: 全模块云回归、实图、独立 PR

**Files:** .github/workflows/animation-mathtex-step2-1.yml; approved spec/plan; existing module README.
- [x] 运行 contract 与 full regression workflow；另设安装真实 Manim + TeX 的 render job。
- [x] 生成实际 package → storyboard → execution 的 smoke，使用真正可见的 m_d_sin 渲染并上传 PNG/JSON artifact。
- [ ] 核验最新 commit 云 CI 全绿、真实 PNG 和像素边界。
- [ ] 检查整体 diff、确认未擅自修改教师数学内容；进行代码审查。
- [ ] 开 Draft PR 指向 feature/animation-engine-v1-step1，注明已完成/剩余边界，绝不合并。

## 2.1 Out of scope
不含连续动画、子式高亮、整幕排版、中文题干混排、长题切幕、音频与字幕秒级同步；以上单独开发 2.2—2.5。
