# 数学教师模块 V1.0（独立开发）

本目录只实现 `shipinyinqing` 的**数学教师模块**；不包含题目上传 UI、Web 前后端、TTS、字幕实际时间轴、Manim、渲染、视频微调或 MP4 合成。

> 本版为可执行的结构化教学包生成器，不是已验证数学证明的自动化证明器，也不生成视频。

## 已实现

- **Prompt A**：根据题目与参考解析提取目标、条件、原解法结构、原步骤和依赖，允许标记可追溯的解释性补充；严禁无来源的新解法。
- **Prompt B**：按参考解析安排思维引导、知识点及本题对应，再回到推导/证明；不把所有题目改成固定模板。
- **Prompt C**：生成连贯口播语义、数学 LaTeX 对象、板书动作与数学动画意图；不负责生成动画代码。
- **严格数据合同**：Pydantic 2；模型多余字段拒绝，结构化内容最终生成 `TeachingPackage`。
- **确定性规则校验**：来源 ID、步骤依赖、参考步骤覆盖、知识点「先讲→本题应用→回推导」顺序、口播/板书/动画引用完整性。
- **字幕**：仅由口播单元确定性投影，不由 AI 独立扩写；真实起止时间留待后续语音模块。
- **有限数学验证**：白名单 AST + SymPy 检查部分代数恒等式；不能验证的其他数学事实标记需人工/专门数学检查。
- **严格阻断**：发现确定错误则中止；遇到未经核实的重要补充默认中止并输出原因。只有显式 `--allow-needs-review` 才可继续输出标记 `needs_review` 的草稿，不会将其伪称通过。

## 本地运行

使用 Python 3.10+：

```bash
cd teacher_module
python -m pip install -e '.[test]'
python -m pytest -q
```

配置 OpenAI-compatible Chat Completions JSON API；凭据只放在环境变量中，**不要写进仓库**：

```bash
export MATH_TEACHER_API_KEY='your-secret'
export MATH_TEACHER_MODEL='your-model-name'
export MATH_TEACHER_BASE_URL='https://your-provider.example/v1'
math-teacher run examples/limit_input.json --output output/teaching_package.json
```

在 Windows PowerShell 中使用 `$env:MATH_TEACHER_API_KEY="..."` 等环境变量。服务端必须兼容 `/chat/completions` 及 `response_format={"type":"json_object"}`；如果支持严格 JSON Schema，可加 `--schema-mode`，但某些兼容服务不支持 Pydantic 生成的复杂严格 Schema。

需要人工复核的场景默认会停止；仅为生成可供人工核查的草稿，可加 `--allow-needs-review`。它**不是自动数学验收开关**。已确认的数学错误和结构错误仍会阻断。

查看正式合同：

```bash
math-teacher schema input --output input.schema.json
math-teacher schema package --output package.schema.json
```

## 输入合同

最简输入：

```json
{"problem":"完整原题","reference_solution":"对应的完整参考解析"}
```

支持由上游输入模块提供 `problem_segments`、`solution_segments`，每个元素包括 `source_id`、`text`、`kind`；未提供时，程序只为**完整字段**分配 `problem:0` 和 `solution:0` 两个真实来源 ID，不会伪造细粒度 OCR 行号。图片和 PDF 的提取不在本模块开发范围内。

输出为 `TeachingPackage`，包含 `source`、`understanding`、`plan`、`lesson`、`subtitles`、`validation`、哈希和 Prompt 版本。

## 数学与工程边界（重要）

1. `ready_with_limits` 表示**程序执行的结构验证通过**，不是宣称整个复杂证明在数学上已形式化验证。原参考解析可能仍需人工复核。
2. 自动数学检验目前只支持安全白名单代数表达；涉及除法定义域、参数条件、洛必达、泰勒余项、极限、复杂证明或矩阵定理时不自动宣称证明成功。
3. Prompt 是可迭代基线。不同模型的 JSON 质量及教学质量要通过真实题库验收；一次成功调用不代表稳定生产。
4. 教师口播中的显示 LaTeX、数学读音意图、正式 TTS 合成是不同数据层。数学变量保留标准写法，未来语音模块再实现精确发音。
5. 当前模块不会自动扫描/修复被模型省略的整段原解析语义，也无法根据任意自然语言解析证明每句话成立；来源覆盖检查是可追溯**结构检查**，不是完整语义证明。
6. 跨模型的严格 JSON Schema 兼容性、实际 LLM 端到端讲解质量尚未在没有真实 API 凭据时实测；本地测试使用模拟模型验证编排和失效行为。

## 开发边界

本包通过 `JsonModel` Protocol 可替换模型适配器。不得反向依赖 V2 项目包路径，不应在这里添加前端、语音、Manim 或视频合成功能。
