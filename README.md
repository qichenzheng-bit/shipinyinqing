# 微光数学 · Windows 电脑 App 1.0.8

**Windows 单平台最终交付。** 微光数学是一款考研数学教学视频制作程序，覆盖数学教师草稿、数学审核、课堂编排、教学讲稿审核、逐步板书、Manim/LaTeX 渲染、神经网络语音配音、字幕、视频下载与多轮微调。当前版本最终只发布 **Windows 安装版 EXE** 和 **完整源码维护 ZIP** 两份文件，不再发布免安装版、移动端或 Linux 安装包。

最终运行界面是独立的 Windows Electron 桌面应用（不是提供一个浏览器网址作为 App）。底层工作台与本地 FastAPI/容器服务协作；**界面并未重写为纯 WinUI 原生组件，视频生产需要外部运行环境，安装包不是纯离线一体化可执行文件**。

## 1. 下载安装

打开 [Windows App 构建工作流](.github/workflows/windows-desktop.yml)，下载最新成功的 `main` 分支附件 `WeiGuang-Math-Windows-v1.0.8-Installer-and-Source`。附件里**只有两份最终文件**：

| 文件 | 用途 |
|---|---|
| `WeiGuang-Math-Setup-1.0.8-x64.exe` | **使用版**：Windows 10/11 x64 安装程序，安装后从桌面启动，支持选择安装目录 |
| `WeiGuang-Math-Source-1.0.8.zip` | **维护版**：完整的前后端、桌面客户端、数学/视频引擎、配置示例、持续集成脚本、必要回归测试源码和测试构造器；方便后续更新修改 |

这两份文件来源于同一个 GitHub 提交。源码 ZIP 的根目录内包含 `release-manifest.json`，注明 Git 提交、版本、安装包 SHA-256 和源码文件逐项 SHA-256，方便核对与维护。交付包内不会再单独提供便携版 EXE、测试成片、字幕、截图、数据库副本或演示数据。

**安装过程中自动准备依赖**：Windows 安装向导新增「自动下载并安装所有缺少的运行依赖」选项（默认勾选），通过 Microsoft WSL、Windows 软件管理器、Docker 官方签名安装程序、Node.js 官方 SHA-256 清单及 npm 官方仓库自动安装 WSL2、Docker Desktop、Node.js、Codex CLI、Gemini CLI 和 CodeBuddy CLI。**无需自行寻找、下载或执行这些第三方安装包。** 已安装组件跳过；网络或重启导致中断时，打开微光数学点击「自动配置环境并进入工作台」即可继续。Manim/TeX/FFmpeg、PostgreSQL、Redis 和 Python 环境则由自动构建的 Docker 镜像准备，不需要单独安装。**安装包不是离线免下载版本**，下载仍需要网络、磁盘空间和系统权限；Docker Desktop 首次使用条款及第三方 AI 账号的网页登录必须由用户确认。源码 ZIP 编辑后可重新构建安装包。

安装包尚未配置 Windows 代码签名证书，**公开发行前需要购买/配置可信签名证书并通过安全审查**。不能把未经签名的内部构建称为已取得可信发行者认证的软件。

### 运行模式 A：本地完整视频引擎（推荐）

双击 `WeiGuang-Math-Setup-1.0.8-x64.exe`，在安装向导勾选自动准备依赖并完成安装。安装程序会检测并下载必要组件；若提示 WSL2 需要重启，请重启电脑。随后直接打开「微光数学」，点击「本地视频引擎 → 自动配置环境并进入工作台」。**无需自行前往 Docker、Microsoft 或 npm 网站下载运行依赖。**

1. 首次启动将自动构建 Docker 容器，准备 PostgreSQL 数据库、Redis、FastAPI、Celery Worker，以及 Manim/LaTeX/FFmpeg 等视频渲染依赖；这一步需要较大的下载和编译开销。
2. App 生成并通过 Windows 凭据系统加密保存本地数据库密码、登录密钥和模型密钥保护材料，自动完成本地服务身份验证与登录。
3. 进入工作台「设置 → 配置 AI 模型」，可选择 Codex、Gemini 或 CodeBuddy 官方 CLI 进行账号授权并从下拉菜单选择模型；也可使用已有 API Key 连接。
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

### 一键安装的范围与可恢复性

安装向导默认勾选**自动安装依赖**；取消勾选只会安装微光数学本体，之后仍可在应用的本地引擎启动页一键补齐。安装动作仅配置当前机器所需的 WSL2、Docker Desktop、Node.js、三个官方 CLI 与视频引擎容器；**不会移除已有的 PostgreSQL Docker 卷、视频、历史记录、账号登录信息或用户配置**。

若 Windows 首次启用 WSL2 需要管理员权限，安装过程会弹出正常的 Windows 用户账户控制（UAC）提示；启用后可能需要你自行重启 Windows。WSL2 本身还要求硬件虚拟化受支持且在固件中启用，安装程序不能安全地替你修改 BIOS。Docker Desktop 首次启动会在其官方窗口处理许可和服务配置；如果账号策略或网络阻断安装，系统会显示失败并允许重试，**不会假装已经配置成功**。三家 AI 账号仍需各自官方网页登录。

系统依赖分两个阶段准备：安装 EXE 时下载基础组件；首次打开微光数学时启动 Docker Desktop，并自动通过 Docker Compose 拉取镜像、构建 Python/TeX/FFmpeg/Manim、数据库和任务服务。容器构建依赖互联网，可能需要较大磁盘容量，但全程不要求另外下载第三方安装包。

### 全局 AI 模型与 Windows CLI（v1.0.8）

在「设置 → 配置 AI 模型」中**只选择一次模型**，统一应用到数学教师 A/B/C、解题与数学审核、知识点、教师口播、课堂编排、归纳总结和多轮自然语言微调。每项已提交任务会锁定当时的型号、推理强度和超时，切换型号只影响新任务。

**四种模型入口：** Codex CLI、Gemini CLI、CodeBuddy CLI，以及原有 API 连接。桌面 App 的「登录账号」按钮仅为这三家官方 CLI 发起登录，使用官方网页授权，不在微光数学收集账号密码。首次点击会自动启动该 CLI 的受控 Windows 登录控制台：Codex 通过 `codex login` 打开浏览器，Gemini 需要在官方向导中选择「Sign in with Google」，CodeBuddy 需要先选择国内、国际或企业登录方式，随后由官方 CLI 打开浏览器。**仅仅打开厂商官网并不会让 CLI 获得授权，因此不使用固定网站链接冒充登录完成。** 授权结束后需在微光数学里「检查登录状态」及「测试当前模型」；Gemini/CodeBuddy 在没有可靠非交互登录状态命令时显示「待验证」，不会擅自显示已登录。

**模型版本使用下拉选择。** Codex / Gemini 默认提供候选型号；CodeBuddy 同时读取用户本机 `~/.codebuddy/models.json` 的型号 ID（不会读出密钥）。API 服务商支持查询实际返回的模型列表；没有列表接口时可以先通过「添加其他型号」加入下拉选项。候选型号不代表账号一定能用，最终需通过真实调用验证。仅保留以上三个 CLI 平台，不包含其他桌面助手的适配逻辑。

**CLI 桥接安全**：Windows Electron 主进程调用本机 CLI。Docker Worker 只通过 PostgreSQL 私有任务队列提交教学 JSON，请求由 Windows App 以两个独立随机密钥主动轮询、领取和回传。不会复制 CLI 登录凭据到容器，不额外监听网络端口。Codex 使用只读沙盒，Gemini 和 CodeBuddy 使用计划模式；输入通过 stdin 传送，执行器只接受固定的工具名和受控模型 ID/参数。结果必须通过 JSON 和现有数学教学契约校验，未通过不能成为正式教学视频。**关闭 Windows App 将使 CLI 调用不可用**，并不影响已有 API 模式。

安装版会自动安装尚缺少的三个官方 CLI，但不会提供任何第三方账号授权或付费额度。在 Windows 本地 App 进入「配置 AI 模型」，选择三家 CLI 之一、点击「登录账号」并完成官方认证，再通过「测试当前模型」进行真实 JSON 测试，最后应用到整个教学流程。远程 HTTPS 模式不暴露任何 Windows 登录控制接口。自动化测试验证模型锁定、数据库队列、JSON 和安全性，但**不能代替你在自己 Windows 电脑上用真实 Codex/Gemini/CodeBuddy 账号做首次验收**。套餐、额度、地区限制以及型号开放情况由各服务商决定。

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
| `desktop/` | Windows Electron 应用、桌面 Logo、NSIS 安装程序、官方依赖下载向导与回归测试 |
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

### 最终安全检查（v1.0.8）

- **官方登录隔离**：仅保留 Codex、Gemini、CodeBuddy CLI，本地 Windows 工作台发起官方浏览器授权；不接收第三方账号密码、不复制 CLI 登录 Token，也不允许远程 HTTPS 页面调用 Windows 登录功能。
- **最小环境变量**：CLI 只继承执行所需的 Windows 用户目录、PATH、locale 与网络代理环境；不再把主程序环境里的 API Key、数据库密码、云密钥或 `NODE_OPTIONS` 直接传给模型子进程。自定义的 Gemini 模型配置仅以一次性路径传入。
- **浏览器保护**：增加 CSP 限制脚本、图片与请求来源，阻止网页嵌入、禁止嗅探、移除 Referrer，并禁止 API 数据被浏览器缓存；Cookie 仍需同站验证，修改类请求仍需通过同源检查。
- **交付内容白名单**：源码 ZIP 和仓库审计拒绝任意嵌套目录中的真实 `.env`、凭据、Token、私钥、个人数据库及生成媒体；保留非敏感 `.env.example` 模板及真正的数学回归测试。
- **不删除真实数据**：安全清理仅针对可重建的 CI/构建缓存。PostgreSQL `pgdata`、教学视频 `lessondata`、模型登录信息和真实微调记录不受自动删除影响。

发布验证涵盖 Windows 真实启动、前后端 UI、PostgreSQL、CLI 进程隔离、浏览器安全响应头、源码清单与双文件 SHA-256。**自动化验收不等于第三方真实账号登录或你本机完整视频生成已验证。** Windows 安装包仍未配置代码签名证书，公开发行前应签名并做可信供应链审查。

## 5. 验收说明

- `system-ci.yml`：仅在 Windows Runner 执行源码、教师/导演/后端/动画引擎非渲染测试、Docker Desktop Compose 配置和真实课程讲稿生成核验。
- `frontend-screenshots.yml`：仅在 Windows Runner 执行真实 Chromium UI 自动化截图以及水印单帧验证，生成物由 CI 临时保存，流程结束即丢弃。
- `windows-desktop.yml`：Windows 11 原生 Electron 窗口、唯一 NSIS 安装包构建、完整源码 ZIP 构建、严格的两文件清单和 SHA-256 校验。
- `final-new-question.yml`：新数学题的真实 Manim、Edge TTS、字幕、60 FPS、视频水印及总结板书成片验收；成片只用于临时 CI 核验，不再作为交付物上传。此特殊媒体验收仍使用 Linux CI 环境模拟 Windows Docker Desktop 内的 Linux 容器工具链；**它不构建、安装或交付 Linux 版 App**。

自动化通过不等于已在你的 Windows 电脑完成 Docker Desktop 初始化、实际大模型账单/接口验证或本地渲染；首次安装后请亲自完成一次完整题目的录制与下载。正常更新客户端不应主动清理原视频与数据库卷。

发布时间：2026-11-02；两文件最终交付版本：**微光数学 Windows App v1.0.8**。以 GitHub `main` 上的源码及相应 Windows 构建产物为准。
