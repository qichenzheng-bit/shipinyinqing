# 考研数学教学视频引擎 · 项目总说明

> **项目唯一用户说明文档**｜整合版本：V2.7（含 V2.6.6 稳定能力、真实课堂讲稿规范及 60 FPS 默认配置）｜2026-11-01  
> 项目定位：面向考研数学基础较弱或中等学生的**真实教师式**教学视频制作引擎。当前主要完成结构化教学、数学动画、有声视频、事件同步及多轮微调的后端计算引擎；**不等于 Web 前后端和自动解题生产系统已经全部完成**。
>
> 本文档以当前整合代码为准。早期各阶段文档已经精简，仍可通过 Git 历史恢复。**程序必需的四份教师提示词**（`teacher_module/src/math_teacher/prompts/*.md`）虽为 Markdown，但属于运行时代码资源，必须保留；它们不是额外的用户说明文档。

## 1. 系统目标与已确认的课堂规范

教师的教学顺序必须围绕学生理解问题展开，而不是逐项念公式：

1. **开场完整读题**：独立题默认“同学们大家好，我们先来看一下这道{准确题型}题。”之后直接口播原题背景、条件、小问和选项。禁止“我们来读一下这道题”等额外报幕，也禁止漏读、任意改写和重复念同一个题干。
2. **思考引导**：先观察具体数学结构、寻找关系并解释选择依据，**再自然引出方法名称**。如换元积分：先注意 `x²` 与 `2x` 的导数关系，再说明“这就是换元法”，禁止尚无依据就反问“为什么考虑换元法”。
3. **核心知识点穿插**：在首次必要应用处独立强调真正的公式、定理、性质、定义、判定或可迁移方法，说明适用条件和本题对应关系，紧接着用于具体求解；不要把普通移项、心算包装成知识点。
4. **完整、适度的逐步解答**：关键变形、必要中间等式、积分限变换、图形动作都要讲清，不能跳步骤，也不能把每次心算拆得机械冗长。老师讲到哪里、板书写到哪里；已讲过且保留在画面的式子无须反复念。
5. **易错点就地提醒**：指出真实易错操作、出错原因和正确做法，紧贴有风险的推导步骤；不生成空洞警告。
6. **结论后单独归纳**：先答完整结果、证明目标及各小问，**然后**简要回顾本题的识别依据、关键公式或方法和有价值的易错点。总结不重复抄写答案、不强制新加一个公式。

统一白色课堂背景、题干尽量顶部居中、解析与公式黑色、思路蓝色、核心知识紫色、易错点红色、归纳总结绿色。板书直接写在背景上，不加装饰性卡片或答案框；只在写满、安全的教学节点擦板。长证明、矩阵、几何等按需切幕并继承必需的已得结果；短式可一行多步，长式分行，避免重叠。画图先讲明对象，话语对应图形逐笔出现，公式以 MathTex 显示，字幕与发音处理层严格分离。

## 2. 架构与数据流

| 目录 | 职责 | 主要实现 |
| --- | --- | --- |
| `teacher_module/` | 数学教师：输入理解、参考解法结构、教学事件/知识点、自然讲稿、结构化数学来源与有限核验 | `src/math_teacher/{pipeline,validator,models,provider}.py`，`prompts/*.md` |
| `visual_director/` | 教学视觉导演：将教学包转为可验证分镜、布局、板书动作、数学来源与字幕锚点 | `src/visual_director/{director,models,geometry}.py` |
| `animation_engine/` | 真实 MathTex/Manim、白板布局、分幕与图形、神经语音与字幕、完整讲稿审核、60 FPS 视频生成、微调及缓存 | `src/animation_engine/`，`tools/`，`tests/` |
| `.github/workflows/system-ci.yml` | 当前统一源码、教学脚本和非渲染回归质量门槛 | GitHub Actions |
| `README.md` | 项目唯一面向维护者的总说明、使用与状态 | 本文件 |

主要流程：

```text
用户提供原题与参考解析（可信来源）
  → 教师 A：识别题目目标、条件、参考解法和依赖
  → 教师 B：教学规划、思路/知识点/易错点和步骤对应
  → 教师 C：自然教师讲稿 + MathTex/板书/图形意图
  → 源与数学结构核验、人工审阅
  → 视觉导演分镜/教学事件/对象 ID
  → V2.7 完整口播及板书脚本导出（JSON + Markdown），预渲染审核
  → （明确授权制作时）真实 TTS + 逐动作时间轴 + Manim + 字幕 + 60 FPS MP4
  → 多轮自然语言微调：每轮只发布最新通过验证的 MP4
```

数学事实的正确性不能由文件 SHA 或通过了 JSON Schema 就证明；复杂证明、定理适用条件、AI 新增步骤仍需数学审核。未配置模型凭证时不自动调用外部 AI，不会虚构已经完成的数学自动验收。

## 3. 版本与模块能力

| 版本范围 | 当前已完成的核心能力 |
| --- | --- |
| V1–V2.4 | 教师输入合同、视觉导演、来源可追溯的数学书写、布局、长板书分页与实际 MathTex/Manim |
| V2.5.1–2.5.4 | 多项积分、矩阵和行列式、长证明及分类、图形与积分区域 |
| V2.6.1–2.6.3 | 多阶段统一课堂、自适应图形保留和跨幕数学记忆 |
| V2.6.4 | 实际 Edge 神经配音、与语音短句对齐的板书/绘图/字幕 |
| V2.6.5 | 文字提出多个修改要求、多轮连续微调、审阅/反馈、失败回滚、最新 MP4 和单一 JSON 会话记录导出 |
| V2.6.6 | 实际 PCM、字幕图像、分幕和事件级缓存；按数学来源与画面状态精确失效、安全回退 |
| V2.7 | 真实教师自然讲解规范，先核对完整讲稿，再制作视频；题干完整口播、核心知识点先讲再用、易错点、结果之后独立总结 |
| 视频默认 60 FPS | 全部**新**视频和新建微调会话默认 60 FPS；显示分辨率 1280×720；明确指定旧 FPS 仍支持；跨幕擦板按 0.6 秒计算（30 FPS 18 帧、60 FPS 36 帧） |

### 口播与字幕

- 可配置 `zh-CN-YunxiNeural`（云希）和 `zh-CN-XiaoxiaoNeural`（晓晓）。
- 缺省 `speech_rate="+1%"`，旧版为 `-4%`，名义上约快 5%；实际时长必须以真实 PCM 测量为准。
- 每条新的数学板书与图元动作有语音来源锚点；TTS 发音文本、屏幕 LaTeX 与字幕显示文本是不同的数据层。字幕**只由真实口播生成**，不为未读出的标题/式子造字幕。
- 新 V2.7 课程必须导出并审查完整的 `lesson_script.json` 与 `lesson_script.md`，渲染前再次校验来源、实际句子与脚本一致。脚本验证**不等于**自动证明语义正确，真实音画仍需观看验收。

### 微调规则与性能

用户可用自然语言一次提出多个修改意见，对最新视频继续修改直到满意；对外仅显示最终的最新成片，不强制比较原视频或保留多个可见版本。会话内部保留回退所需源快照。所有成功、失败、原始指令、操作与满意反馈以**单一 JSON**保存并可导出。无源审核的新数学事实会被阻断，不得只靠 AI 自述认可。

缓存键包括真实语音、音色、语速、MathTex、数学来源、布局、帧率、媒体版本等，严格核对后才复用。不能保证每次修改都局部渲染，也不能承诺任何题型均按同一倍率加速。旧版性能实验曾观察到 181 秒降为 74 秒（单一任务，非普遍保证）。提升为 60 FPS 可能增加帧渲染/编码开销，尚未对新帧率做正式性能基准测试。

## 4. 安装、输入与常用命令

Python 3.10+；有声视频制作另需 Manim、LaTeX/dvisvgm、FFmpeg/ffprobe、中文字体，以及可访问的 Edge TTS。单纯测试、生成讲稿不需要 TTS/Manim/FFmpeg。

```bash
# 开发安装与不渲染的完整回归
python -m pip install -e './teacher_module[test]' -e './visual_director[test]' -e './animation_engine[test]'
(cd animation_engine && python -m pytest -q -m 'not render')
(cd teacher_module && python -m pytest -q)
(cd visual_director && python -m pytest -q)
```

### 教师教学包（可选接入外部兼容模型）

输入最少提供 `problem` 和 `reference_solution`；如果参考解法来源不完整，不能冒充审核成功。仅在用户实际授权接入模型时设置环境变量：

```bash
export MATH_TEACHER_API_KEY="your-secret"
export MATH_TEACHER_MODEL="your-model"
export MATH_TEACHER_BASE_URL="https://your-provider.example/v1"
math-teacher run teacher_module/examples/limit_input.json --output teaching_package.json
```

外部 API 必须兼容 Chat Completions JSON 响应；密钥只保留环境变量，禁止写入仓库、教案和导出日志。没有授权、网络或密钥时，用已审核的课程样例进行确定性流程测试。

### 只生成完整自然教师讲稿（**不会渲染视频**）

```bash
python animation_engine/tools/build_novel_substitution_integral.py --output lesson-demo
math-animation export-spoken-script \
  --spoken lesson-demo/spoken_classroom.json \
  --output lesson-demo/lesson_script.md
# 同目录生成经源校验的 lesson_script.json
```

此例题为 `I=∫₀² 2x e^(x²) dx=e⁴−1`：先观察 `x²` 与 `2x` 的导数关系，才引出换元法；保留 `I=e⁴-e⁰` 中间过程、积分限风险提示及结论后总结。请勿把这一道题的讲法强套到矩阵、证明、极限等其他题型。

### 未来被明确要求制作真实视频时

```bash
python -m pip install -e './animation_engine[render,test,speech]'
math-animation render-spoken \
  --spoken lesson-demo/spoken_classroom.json \
  --output lesson-demo/lesson.mp4 \
  --manifest lesson-demo/manifest.json \
  --srt lesson-demo/lesson.srt \
  --fps 60
```

**本次代码整理没有调用该命令，也没有进行真实 TTS 或 MP4 渲染。** 如果输入包含 V2.7 合同，必须先完成上面的脚本导出。使用 `--fps 30` 可主动复现历史 FPS；已经产生的旧 MP4 和已有微调会话不会自动转码或改变 FPS。

### 微调 CLI（当前无用户侧 UI）

```bash
math-animation edit-start \
  --package lesson-demo --movie lesson-demo/lesson.mp4 \
  --manifest lesson-demo/manifest.json --session work/edit-session --fps 60

math-animation edit-apply \
  --session work/edit-session --instruction-file feedback.txt \
  --plan reviewed_edit_plan.json

math-animation edit-feedback \
  --session work/edit-session --text "还有一点需要调整"

math-animation edit-export \
  --session work/edit-session --output work/edit_history.json
```

`edit-apply` 也可在用户授权下显式使用 `--ai-config`；若没有审核过的 AI 计划或模型配置，不宣称自动完成任意自然语言请求。对外最新成片在 `work/edit-session/latest.mp4`，字幕为 `latest.srt`。

## 5. 文件保留与维护约定

本轮最终仓库仅有一个**人工阅读的总 Markdown 文档**（根目录本 `README.md`）。原阶段记录、旧规划说明、重复的模块 README 等已从最新版工作树清理；历史内容仍留在 Git 提交历史中，可以追溯或恢复。

**下列四个 Markdown 为程序必需，绝不能删：**

- `teacher_module/src/math_teacher/prompts/global.md`
- `teacher_module/src/math_teacher/prompts/a_understanding.md`
- `teacher_module/src/math_teacher/prompts/b_planning.md`
- `teacher_module/src/math_teacher/prompts/c_narration.md`

原因：教师流水线通过 Python `importlib.resources` **运行时读取**这些文件，且 `teacher_module/pyproject.toml` 已将其声明为包资源。删掉会直接导致 AI 讲稿生成失败。源代码、数据合同、真实题目测试样例、`tests/`、必要的 `tools/` 与项目配置保留；这些都属于系统，不视为垃圾。原有大量按阶段命名的 CI 工作流统一替换为一个有效的 `system-ci.yml`；历史专项测试仍以 Python 测试和 Git 历史保留。

提交新功能时：先检查数学来源与自然教师脚本，执行不渲染回归，只有用户明确要求时才再做真实视频测试。不要把测试数据伪称真实课堂成片。使用独立开发分支、CI、PR 审阅后整合至 `main`。

## 6. 已有验收与仍未实现的部分

已存在的历史真实媒体测试：

- [V2.6 有声编辑/缓存测试](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963404)
- [V2.6 长积分、矩阵、证明的媒体测试](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963398)
- [V2.7 旧版 30 FPS 真实有声积分课程](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41287587995)
- [V2.7 自然教师讲稿（不渲染）](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41289861322)
- [60 FPS 代码/讲稿静态回归（不渲染）](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41290585707)

这些是各提交时点的测试，不表示本次 60 FPS 改动已经完成真实音视频专项验收。本次最终合并以前、以后，以最新主线提交对应的 **非渲染 CI** 为准。

**尚未交付或不应过度宣传的工作：**正式 Web 前端、服务端 HTTP API、Web 端的视频下载按钮和**跨会话的全部微调记录一键 JSON 导出**，以及完全自主的任意题输入→自动数学推理→无人工审查成片流程。当前 CLI 能导出单个微调会话记录、保留 latest.mp4 以供后续下载接口使用，但**Web 按钮和全局批量导出仍需另外开发**。自然语言质量、图形同步、复杂数学证明需在真实新题上持续验收；本次仓库整理不修改这些功能的设计或承诺状态。

## 7. 综合验收条件与安全边界

- 不跳过参考解析中的必要推导；显示 LaTeX、真实口播和字幕一致；复杂题该切幕才切幕，画图不重叠、不遮挡。
- 重要的新公式、定理及方法先解释使用条件再用于本题；题目结论与归纳总结分离；严格遵守用户已认可的自然课堂语言。
- 源哈希、对象 ID、真实 PCM/字幕与缓存来源独立校验。用时、帧率、样例测试通过只说明某个可验证的工程性质，**不代替专业数学或教育学验收**。
- 未经审核的 LaTeX 不得直接送无沙箱的公网渲染服务；需要独立低权限进程、CPU/内存/超时限制。外部 AI 访问使用最小必要权限和明确授权。
- 60 FPS 是新渲染的默认设置，不是对历史 30 FPS 视频一键变帧。需要真实 60 FPS 成片验证时，另行明确安排，不在整理阶段偷偷执行。

---
最后更新：2026-11-01。主线以 GitHub `main` 的实际合并状态和统一质量门禁为准。
