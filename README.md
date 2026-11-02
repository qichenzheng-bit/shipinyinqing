# 微光数学 · Windows 电脑 App 1.0.5

**Windows 单平台最终交付。** 微光数学是一款考研数学教学视频制作程序，覆盖数学教师草稿、数学审核、课堂编排、教学讲稿审核、逐步板书、Manim/LaTeX 渲染、神经网络语音配音、字幕、视频下载与多轮微调。当前版本最终只发布 **Windows 安装版 EXE** 和 **完整源码维护 ZIP** 两份文件，不再发布免安装版、移动端或 Linux 安装包。

最终运行界面是独立的 Windows Electron 桌面应用（不是提供一个浏览器网址作为 App）。底层工作台与本地 FastAPI/容器服务协作；**界面并未重写为纯 WinUI 原生组件，视频生产需要外部运行环境，安装包不是纯离线一体化可执行文件**。

## 1. 下载安装

打开 [Windows App 构建工作流](.github/workflows/windows-desktop.yml)，下载最新成功的 `main` 分支附件 `WeiGuang-Math-Windows-v1.0.5-Installer-and-Source`。附件里**只有两份最终文件**：

| 文件 | 用途 |
|---|---|
| `WeiGuang-Math-Setup-1.0.5-x64.exe` | **使用版**：Windows 10/11 x64 安装程序，安装后从桌面启动，支持选择安装目录 |
| `WeiGuang-Math-Source-1.0.5.zip` | **维护版**：完整的前后端、桌面客户端、数学/视频引擎、配置示例、持续集成脚本、必要回归测试源码和测试构造器；方便后续更新修改 |

这两份文件来源于同一个 GitHub 提交。源码 ZIP 的根目录内包含 `release-manifest.json`，注明 Git 提交、版本、安装包 SHA-256 和源码文件逐项 SHA-256，方便核对与维护。交付包内不会再单独提供便携版 EXE、测试成片、字幕、截图、数据库副本或演示数据。

**使用版并非独立离线渲染器**：安装程序本身不捆绑 Docker Desktop、WSL2、完整 Manim/TeX 运行环境或付费模型密钥；首次使用本地视频引擎仍需要 Docker Desktop 完成环境初始化。**维护版不是可直接安装的软件**，编辑源码后要重新构建 Windows 安装包。系统界面为 Electron 桌面应用。

安装包尚未配置 Windows 代码签名证书，**公开发行前需要购买/配置可信签名证书并通过安全审查**。不能把未经签名的内部构建称为已取得可信发行者认证的软件。

### 运行模式 A：本地完整视频引擎（推荐）

在 Windows 电脑上安装并启动 **Docker Desktop**，启用 WSL2、Linux 容器模式，并确保磁盘空间与网络正常。打开「微光数学」App，点击「本地视频引擎 → 启动并进入工作台」。

1. 首次启动将自动构建 Docker 容器，准备 PostgreSQL 数据库、Redis、FastAPI、Celery Worker，以及 Manim/LaTeX/FFmpeg 等视频渲染依赖；这一步需要较大的下载和编译开销。
2. App 生成并通过 Windows 凭据系统加密保存本地数据库密码、登录密钥和模型密钥保护材料，自动完成本地服务身份验证与登录。
3. 进入工作台「设置 → 管理模型 API」，填写你有权限使用的服务商 API Key 和模型 ID，选择应用于数学教师、课堂编排和微调的模型版本。
4. 创建题目与参考解析，按顺序审核数学内容、课堂编排和教师讲稿，提交 60 FPS 有声视频生产任务；完成后可播放/下载 MP4 并执行多轮微调。

**Windows 是唯一受支持的用户操作系统**。本地模型与视频渲染仍需要 Docker Desktop + WSL2 里的 Linux 容器，这是 Windows 版本的内部依赖，不是另行维护 Linux 系统或 Linux 客户端。

**不需要租用云服务器，也不需要启动 VS Code。** 但本地视频制作不是完全脱离网络：调用在线大模型、Edge 神经语音以及首次依赖安装时需要连接相应服务。若外部模型接口不可达，需要事先准备可信的可用模型资源。

在工作台里设置模型 API 后，并不自动证明你当前具体型号、版本、额度和网络条件全部兼容；需通过真实服务请求验证。不要把敏感模型密钥提交到仓库。

### 唯一数据库：PostgreSQL 17

**不再使用 SQLite。** Windows 本地引擎只允许 PostgreSQL 连接，数据库随 Docker Desktop 的 `postgres:17-alpine` 服务启动。API 与 Celery Worker 通过同一个 `postgresql+psycopg://...` 地址连接，数据保存在命名卷 `pgdata`；课程和视频文件保存在独立的 `lessondata` 卷中，二者都不会随关闭 Windows App 自动删除。

直接单独启动 Python 后端时，必须显式设置 `DATABASE_URL`，而不能依赖工作目录自动生成数据库。缺少 PostgreSQL 连接字符串或配置其他数据库类型将立即报错，不会再隐式创建 `weiguang.db`。Docker Compose 会自动向 API 和 Worker 注入数据库连接字符串；安装 Windows App 的正常本地流程无需手动填写。

**已有数据保护：** 此版本不会自动删除旧 `.db` 文件，也不会自动将 SQLite 数据复制到 PostgreSQL。如果你曾经使用早期开发模式并存有真正的数据，先离线备份旧文件，再做独立的数据迁移和逐表核对，确认记录/视频路径/模型密钥后才能弃用旧库。正式 Docker PostgreSQL 数据不需要再次转换。更新前建议同时备份 `pgdata`、`lessondata`、Windows 加密凭据和全部微调历史；禁止运行 `docker compose down -v` 或擅自清除数据卷。

回归测试同样使用真实 PostgreSQL 17，并为每个测试创建独立的临时 schema，不使用本地 SQLite 作为替代。GitHub Windows Runner 只启动其内置 PostgreSQL 测试服务，不访问用户本机数据库。

本地服务仅监听 `127.0.0.1:8000`，不直接对外网公开。退出 Windows App 不会自动删除 PostgreSQL 数据、视频或正在执行的容器任务。

### 运行模式 B：连接已有 HTTPS 后端

如果你已有部署的微光数学服务器，也可以在**同一个 Windows App** 中选择「连接服务器」，填写受信任的 `https://...` 地址。这是可选方案；本地模式不要求另购服务器。客户端禁止普通公网 HTTP 及不受信任的跳转。

### 全局 AI 模型与 Windows CLI（v1.0.5）

在「设置 → 配置 AI 模型」中**只选择一次模型**，统一应用到数学教师 A/B/C、解题与数学审核、知识点、教师口播、课堂编排、归纳总结和多轮自然语言微调。每项已提交任务会锁定当时的型号、推理强度和超时，切换型号只影响新任务。

**四种模型入口：** Codex CLI（Windows 预先安装、ChatGPT 账号登录；可选具体模型与推理级别）、Gemini CLI（Windows 预先安装、Google 账号登录；Gemini 3 使用 thinkingLevel，2.5 使用 thinkingBudget）、CodeBuddy CLI（预先安装并登录，--model 与 reasoningEffort 按实际 CLI 支持范围使用），以及原先的 API 连接。**WorkBuddy 桌面版和 CodeBuddy CLI 是不同的产品接口**；尚未验证 WorkBuddy 桌面版是否允许外部请求逐次指定模型和推理强度，因此不把其内置模型冒充已经接通。CLI 的型号和权限以真实账号实际可用为准。

**CLI 桥接安全**：Windows Electron 主进程调用本机 CLI。Docker Worker 只通过 PostgreSQL 私有任务队列提交教学 JSON，请求由 Windows App 以两个独立随机密钥主动轮询、领取和回传。不会复制 CLI 登录凭据到容器，不额外监听网络端口。Codex 使用只读沙盒，Gemini 和 CodeBuddy 使用计划模式；输入通过 stdin 传送，执行器只接受固定的工具名和受控模型 ID/参数。结果必须通过 JSON 和现有数学教学契约校验，未通过不能成为正式教学视频。**关闭 Windows App 将使 CLI 调用不可用**，并不影响已有 API 模式。

安装版不会自动安装第三方 CLI，也不会提供第三方账号权限。在本地先确认 CLI 本身能登录并正常工作，然后用界面「测试当前模型」进行真实 JSON 测试，再应用到整个教学流程。自动化测试验证模型锁定、数据库队列、JSON 和安全性，但**不能代替你在自己 Windows 电脑上用真实 Codex/Gemini/CodeBuddy 账号做首次验收**。套餐、额度、地区限制以及型号开放情况由各服务商决定。

## 2. 已保留的视频教学规则

- 真实课堂风格：白色背景、黑色数学运算、问题题干固定在上方；老师讲到哪里，板书按步骤写到哪里，避免提前出现整组解式或不必要的无意义拆解。
- 数学公式使用 LaTeX/MathTex；知识点、思维引导、易错提示有独立视觉样式；图像和长推导依实际内容安排，板书填满后按教学事件完整擦除换页。
- 语音保留晓晓 `zh-CN-XiaoxiaoNeural` 与原有 `zh-CN-YunxiNeural` 音色，按真实讲稿进行配音，字幕只跟随实际讲出的内容，不对单独板书内容虚构语音或字幕。
- 视频默认 1280×720、60 FPS，支持下载、右上角透明 Logo 水印和全局微调历史 JSON 导出。
- **归纳总结为公共固定模块**：在原有简洁口播期间，从已经讲过并完成来源审核的内容中重新板书核心知识点公式与易错点，不在最后一幕再朗读完整解题过程，不凭空造新公式。
- 迭代微调与课堂编排继续受源数学检查和审核约束；失败或重新渲染不会静默覆盖既有成功版本。

其中完整新题视频已在专门真实有声验收流程中测试过；本次 Windows 专版收尾不改变已通过人工核验的教学内容模块。

## 3. 模型服务配置与安全

在 App「设置 → 管理模型 API」配置服务商与对应版本，支持 OpenAI、Anthropic、Gemini、DeepSeek、Qwen、GLM、Kimi、豆包、MiniMax、OpenRouter、xAI、Mistral、Groq、Together、Fireworks、Perplexity，以及符合支持协议的第三方兼容服务和本地 Ollama/LM Studio。实时型号枚举受厂商是否提供模型列表影响；不支持枚举的服务可以输入精确模型 ID。**不承诺所有厂商的所有专有协议都无需适配**，实际能力取决于 API 规范和服务商访问权限。

模型密钥保存在后端并加密管理。Windows 本地模式自动生成所需主密钥；如果使用已有服务器，需自行妥善持有 `WEIGUANG_MODEL_MASTER_KEY`。删除 Windows 当前用户下的加密凭据可能使旧数据库密码及已存模型密钥不可恢复，**卸载/更新前应备份数据库、已有视频、微调记录及凭据**。

## 4. 项目结构与发布边界

| 路径 | 作用 |
|---|---|
| `desktop/` | Windows Electron 应用、桌面 Logo、NSIS 安装版及便携 EXE 构建 |
| `frontend/` | Windows 桌面程序复用的工作台界面与资源；**并非单独对用户交付网页程序** |
| `backend/` | FastAPI、任务队列、课程/项目/视频存储、模型 API 与微调服务 |
| `animation_engine/` | 真正的视频引擎、Manim/LaTeX、音画时间轴、字幕、总结板书和水印 |
| `teacher_module/`、`visual_director/` | 教学内容来源、教师讲稿与板书/图形编排 |
| `config/`、`docker-compose.yml`、`backend/Dockerfile` | Windows 本地 Docker Desktop/WSL2 引擎依赖和安全配置示例 |
| `tools/`、`.github/workflows/` | 安全审计、仅生成物清理、Windows 构建和测试 |

**仅保留根目录这一份供人阅读的 README.md。** 以下四份 Markdown 是教师运行时必需的真实提示词，必须保留：

- `teacher_module/src/math_teacher/prompts/global.md`
- `teacher_module/src/math_teacher/prompts/a_understanding.md`
- `teacher_module/src/math_teacher/prompts/b_planning.md`
- `teacher_module/src/math_teacher/prompts/c_narration.md`

清理的边界：移除无用的移动端源码、APK 编译、移动专用测试以及独立 Linux Nginx 部署示例；保留数学回归测试、生成视频所需模块、模型配置机制、项目数据路径、数据库持久化设计和微调历史。禁止删除真实 `.env`、用户凭据、数据库卷、视频、课程包、审核和反馈数据。仓库源码清理**不**意味着清空某台机器上已有的个人运行数据或 Git 历史。

### 最终仓库清理规则

主分支只保留 Windows 正式运行源码、配置示例、必要测试，以及支持持续验收的 CI 脚本。不提供 Linux 安装程序、Linux 桌面客户端及独立 Linux Nginx 部署模板。早期直接提交的前端页面截图已从源码版本中移除；界面截图由 `frontend-screenshots.yml` 在 GitHub Actions 临时生成用于验收，不再长期上传为发布附件，也不会进入 Git 源码。

两份旧版板书策略 JSON 示例也已移除，因为其中的布局尺寸不再代表当前统一课堂引擎。**必要的数学回归测试素材属于维护代码**：仍被单元测试、Windows 回归检查或真实有声视频验收引用的题目构造脚本和极少量规范化 JSON 夹具保留在源码 ZIP 中，但绝不打入安装 EXE。已经生成的测试视频、音频、字幕、截图和数据库不属于源码包，也不会加入两份最终交付物。

临时打包文件、Windows 可执行文件、验收截图、一次性输出及声音/视频等媒体产物已加入 `.gitignore`，`tools/repository_audit.py` 会拒绝它们被错误提交。 `tools/clean_generated.py` 仅处理明确列出的可重建缓存、构建目录与 CI 截图（先预览，显式使用 `--apply` 才删除）。该工具**不会操作**用户视频库、模型凭据、数据库、课程包、微调记录或历史 Git 提交。

GitHub 旧分支及历史 Action 构建记录不属于主分支运行源码。删除旧分支之前需另外确认哪些分支已合并、哪些仅关闭但未合并，不能用清空历史的方式冒充代码整理。

可用的安全审计及仅生成物清理指令：

```powershell
python tools/repository_audit.py
python tools/clean_generated.py
python tools/clean_generated.py --apply
```

## 5. 验收说明

- `system-ci.yml`：仅在 Windows Runner 执行源码、教师/导演/后端/动画引擎非渲染测试、Docker Desktop Compose 配置和真实课程讲稿生成核验。
- `frontend-screenshots.yml`：仅在 Windows Runner 执行真实 Chromium UI 自动化截图以及水印单帧验证，生成物由 CI 临时保存，流程结束即丢弃。
- `windows-desktop.yml`：Windows 11 原生 Electron 窗口、唯一 NSIS 安装包构建、完整源码 ZIP 构建、严格的两文件清单和 SHA-256 校验。
- `final-new-question.yml`：新数学题的真实 Manim、Edge TTS、字幕、60 FPS、视频水印及总结板书成片验收；成片只用于临时 CI 核验，不再作为交付物上传。此特殊媒体验收仍使用 Linux CI 环境模拟 Windows Docker Desktop 内的 Linux 容器工具链；**它不构建、安装或交付 Linux 版 App**。

自动化通过不等于已在你的 Windows 电脑完成 Docker Desktop 初始化、实际大模型账单/接口验证或本地渲染；首次安装后请亲自完成一次完整题目的录制与下载。正常更新客户端不应主动清理原视频与数据库卷。

发布时间：2026-11-02；两文件最终交付版本：**微光数学 Windows App v1.0.5**。以 GitHub `main` 上的源码及相应 Windows 构建产物为准。
