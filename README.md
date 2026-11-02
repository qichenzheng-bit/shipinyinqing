# 微光数学 · Windows 电脑 App 1.0.2

**Windows 单平台最终交付。** 微光数学是一款考研数学教学视频制作程序，覆盖数学教师草稿、数学审核、课堂编排、教学讲稿审核、逐步板书、Manim/LaTeX 渲染、神经网络语音配音、字幕、视频下载与多轮微调。当前发布版本只提供 **Windows 安装版和 Windows 免安装版**，不再维护移动应用或移动端打包流水线。

最终运行界面是独立的 Windows Electron 桌面应用（不是提供一个浏览器网址作为 App）。底层工作台与本地 FastAPI/容器服务协作；**界面并未重写为纯 WinUI 原生组件，视频生产需要外部运行环境，安装包不是纯离线一体化可执行文件**。

## 1. 下载安装

到 [Windows App 构建工作流](.github/workflows/windows-desktop.yml) 打开最新成功的 `main` 分支构建，下载名为 `WeiGuang-Math-Windows-Only-1.0.2-App` 的构建附件，解压后得到：

| 文件 | 功能 |
|---|---|
| `WeiGuang-Math-Setup-1.0.2-x64.exe` | **推荐**：Windows 10/11 x64 安装版，支持选目录、开始菜单与桌面快捷方式 |
| `WeiGuang-Math-Portable-1.0.2-x64.exe` | 免安装版，可直接运行 |
| `SHA256SUMS.txt` | Windows 文件校验值 |
| `app-manifest.json` | 版本、源码提交 SHA、打包资源和签名状态 |

两个 EXE 都是桌面应用，不需要打开 VS Code，也无需手工运行 Web 浏览器。安装版与便携版的功能相同。Windows 程序图标采用项目已经确定的“展开书页 + 暖金星芒”，视频右上角使用相应透明水印。

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

主分支只保留 Windows 正式运行源码、配置示例、必要测试，以及支持持续验收的 CI 脚本。不提供 Linux 安装程序、Linux 桌面客户端及独立 Linux Nginx 部署模板。早期直接提交的前端页面截图已从源码版本中移除；新的界面截图由 `frontend-screenshots.yml` 在 GitHub Actions 中重新生成并作为构建附件保存，不再进入 Git 历史的新提交。

两份旧版板书策略 JSON 示例也已移除，因为其中的布局尺寸不再代表当前统一课堂引擎。**真实的数学测试素材并非无关文件**：仍被单元测试、Windows 回归检查或真实有声视频验收引用的测试题必须保留在测试目录，不会打入用户安装 EXE。

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
- `frontend-screenshots.yml`：仅在 Windows Runner 执行真实 Chromium UI 自动化截图以及水印单帧验证。
- `windows-desktop.yml`：Windows 11 原生 Electron 窗口、NSIS 和便携 EXE 构建及文件资源、SHA-256 校验。
- `final-new-question.yml`：新数学题的真实 Manim、Edge TTS、字幕、60 FPS、视频水印及总结板书成片验收。此特殊媒体验收仍使用 Linux CI 环境模拟 Windows Docker Desktop 内的 Linux 容器工具链；**它不构建、安装或交付 Linux 版 App**。

自动化通过不等于已在你的 Windows 电脑完成 Docker Desktop 初始化、实际大模型账单/接口验证或本地渲染；首次安装后请亲自完成一次完整题目的录制与下载。正常更新客户端不应主动清理原视频与数据库卷。

发布时间：2026-11-02；最终单平台版本：**微光数学 Windows App v1.0.2**。以 GitHub `main` 上的源码及相应 Windows 构建产物为准。
