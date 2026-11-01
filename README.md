# 微光数学 · 考研数学教学视频系统

微光数学是一套用于**考研数学教学视频**的工具：数学教师生成可审查的教学草稿，课堂编排模块将题解映射为板书/口播动作，动画引擎以 Manim、LaTeX、TTS 和 FFmpeg 制作视频。完整视频流程不跳过数学来源核验和教师人工审查。

本仓库同时提供白底、黑字的 Web 工作台、FastAPI 后端和 **Windows 桌面 App**。Windows 图标沿用现有“翻开的书 + 暖金色星芒”，桌面安装包可创建开始菜单和桌面快捷方式；右上角教学视频水印仍使用适合白色板书的透明标志。

## 1. 选择运行方式

| 方式 | 使用场景 | 必要条件 |
|---|---|---|
| **Windows Setup.exe** | 下载安装后从桌面直接打开工作台 | Windows 10/11 x64；本地生产需要 Docker Desktop + WSL2 |
| **Windows Portable.exe** | 免安装的便携桌面客户端 | 与安装版相同的后端条件；不自带 Docker |
| **Web 工作台** | 浏览器访问本机或已部署服务器 | 服务端 FastAPI、数据库、Redis、Celery/视频引擎 |
| **Python CLI** | 开发与验收视频引擎、细粒度调试 | Python 3.11+、相应媒体工具和模型资源 |

**桌面 App 不需要打开 VS Code**。本地模式由 App 启动 Docker 视频服务，调用本仓库原有后端和引擎；服务器模式通过**HTTPS**连接已部署的同一套系统。**桌面安装包不是把 Manim、TeX、Docker 和所有大模型合成一个纯离线 EXE**，首次本地启动需构建/下载依赖，真实 TTS 和在线模型需要网络。

### Windows 桌面安装包

Windows 安装与便携包由 [WeiGuang Math Windows Desktop installer](.github/workflows/windows-desktop.yml) 在 GitHub Actions 的原生 Windows Runner 构建。打开该 workflow 最新成功运行，下载附件 `WeiGuang-Math-Windows-Setup-and-Portable`，其中包含：

- `WeiGuang-Math-Setup-1.0.0-x64.exe`：Windows 安装包（NSIS，支持选择目录、创建快捷方式）
- `WeiGuang-Math-Portable-1.0.0-x64.exe`：Windows 便携版

安装后启动「微光数学」，选择 **本地视频引擎** 或 **连接服务器**。安装包图标由 `desktop/tools/generate_app_icon.py` 生成 ICO/PNG，完全复用项目的书页与金色星芒元素，无需下载安装外部字体。

Windows 本地模式首次运行：

1. 安装并启动 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)；启用 WSL2，确保 Linux 容器模式可用。
2. 在 App 中点击「启动并进入工作台」。首次启动会拉取 Docker 镜像、编译媒体依赖，磁盘和网络开销较大。
3. App 会生成随机本地登录密钥和数据库密码，在当前 Windows 用户配置目录中以系统凭据加密保存；验证本地服务身份后再自动登录。
4. 在「设置 → 管理模型 API」保存服务商/API Key，选择当前账号可用的模型版本。创建题目，依次完成数学审核、课堂编排审核、讲稿审核，然后制作视频。
5. 关闭 App 窗口不会强制杀死正在运行的 Docker 容器；视频数据由持久化 Docker 数据卷保存。

**不要删除 Windows 应用用户目录下的本地凭据**，否则可能无法连接旧 PostgreSQL 数据卷及解密模型 API Key。卸载前应备份数据库、全部视频和微调记录。App 本地服务默认绑定宿主机回环地址 `127.0.0.1:8000`，不是公网端口。

已有华为云或其他服务器的用户可选择「连接服务器」，填写 `https://你的域名`，在原网页登录。为了保护密钥，不允许通过公共 HTTP 地址连接，**不应把未配置 TLS 的内部服务直接暴露公网**。

Windows 安装包目前未配置代码签名证书；Windows SmartScreen 可能显示未知发布者提示。若准备公开发行，请配置真实签名证书、版本升级策略及安全审计，不能绕过安全检查。

### 开发者运行桌面项目

```powershell
# 项目根目录；Windows + Node.js 24 + Python 3.11+
python -m pip install Pillow
python desktop/tools/generate_app_icon.py --output desktop/build
cd desktop
npm install
npm test
npm start
# 实际构建 Windows 安装包：
npm run build:windows
```

只要客户端显示桌面窗口，不代表后台的视频生产已启动。**本地容器成功启动及真实 Manim/TTS 生成需要设备现场验证**。

## 2. 数学教学及视频流程

```text
输入题目、参考解析
  → 数学教师 A/B/C 生成教学草稿
  → 人工核对数学
  → 课堂编排候选（知识点、思维引导、逐步板书、口播）
  → 人工审核课堂编排
  → V2.7 严格来源校验与完整讲稿
  → 人工批准讲稿
  → Celery 任务执行 Manim / TTS / FFmpeg
  → 60 FPS MP4、字幕、视频右上角 Logo
  → 自然语言微调 → 核对修改候选 → 生成新版 → 满意后导出记录
```

讲解质量遵循实际考研数学课堂约定：题目原文保留；教师讲到哪里，板书在哪里逐步显现；数学变量保留规范 LaTeX 显示，TTS 读音映射独立处理；字幕只记录真正讲出的内容；较长证明和多积分运算按需分幕，不制造无意义拆解；结论与归纳总结相互独立；总结只回顾之前使用过的核心知识点、公式与易错点。

未经过数学审核的模型输出**不会仅凭 JSON 合法就直接当作正确题解**。全部微调要求、候选计划、人工审核与反馈均归档；视频采用独立版本路径，重新生成或失败不覆盖旧成功视频。一个全局导出接口生成全部会话历史 JSON，供后续优化模型使用。

## 3. API 与模型配置

在网页「设置 → 管理模型 API」选择服务商：OpenAI（Chat Completions / Responses）、Anthropic Claude、Google Gemini、DeepSeek、Qwen、GLM、Kimi、豆包、MiniMax、OpenRouter、硅基流动、xAI、Mistral、Groq、Together、Fireworks、Perplexity、本地 Ollama/LM Studio，以及自定义兼容接口。

优先尝试服务商实时模型列表；不支持枚举时输入完整模型 ID 或版本。可以将一个精确版本同时应用于**数学教师、课堂编排、视频微调**，也可以为每个模块独立选择。创建任务时固定模型/服务商版本，防止排队后静默切换。模型真实兼容性由小规模 JSON API 调用验证，可能产生厂商计费；不是所有图像、音频或专有协议模型都适用。

模型 API Key 在服务端加密存储。云端部署时要设置稳定的 `WEIGUANG_MODEL_MASTER_KEY`，可用：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将生成值存入私有 `.env`，**不要提交到 Git**。Windows 桌面本地模式会自动生成并使用 Windows 凭据保护，不需要你手工填入主密钥。

本地模型（Ollama/LM Studio）通过 Windows Docker Desktop 的 `host.docker.internal` 访问宿主机时，需要确认服务允许该地址访问。启用 `WEIGUANG_ALLOW_PRIVATE_MODEL_ENDPOINTS=1` 前请了解私网连接风险；公网服务器默认禁用。

## 4. 服务器与 Web 工作台

仅部署网页时：

```powershell
Copy-Item .env.example .env
# 使用文本编辑器填写随机 POSTGRES_PASSWORD、WEIGUANG_API_TOKEN 等必要私有配置
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

本机访问 `http://127.0.0.1:8000/`。公网部署使用 Nginx + HTTPS，示例为 `deploy/nginx/weiguang.conf.example`。当前 Docker 服务包含 PostgreSQL、Redis、API、Celery Worker；视频实际渲染需要相应 FFmpeg/LaTeX/Manim/TTS 运行环境以及网络访问。

Web 提供：题目与项目增删改查、批量删除与回收站恢复、数学草稿审核、课堂编排审核、讲稿批准、视频预览与下载、多轮微调、后台任务状态及全局 JSON 导出。前端布局保持白底、黑字、浅灰线条，避免无关介绍文字。

## 5. 仓库结构与清理边界

| 目录 | 作用 |
|---|---|
| `teacher_module/` | 教师理解、规划、讲稿及数学来源核验 |
| `visual_director/` | 数学板书布局和导演信息 |
| `animation_engine/` | Manim、LaTeX、语音、时间轴、字幕、60 FPS 与多轮微调 |
| `backend/` | FastAPI、任务队列、数据模型、模型 API 接入及视频服务 |
| `frontend/` | 轻量黑白 Web UI、当前 Logo 与已验收浏览器截图 |
| `desktop/` | 安全 Electron 桌面壳、启动页、Windows ICO 构建与安装封装 |
| `tools/` | 仓库完整性审计和仅清理生成物的安全工具 |
| `config/`、`deploy/` | 无密钥示例、服务器部署模板 |
| `.github/workflows/` | Windows/Linux 核心测试、浏览器截图、Windows 安装包构建 |

**仅根目录本 README 是供人阅读的项目 Markdown 文档。** 以下四份 `.md` 为程序运行时读取的教师提示词，绝不可删除：

- `teacher_module/src/math_teacher/prompts/global.md`
- `teacher_module/src/math_teacher/prompts/a_understanding.md`
- `teacher_module/src/math_teacher/prompts/b_planning.md`
- `teacher_module/src/math_teacher/prompts/c_narration.md`

测试、fixtures 和验收脚本属于数学正确性与前后端回归门禁，不能当作无关文件随意删除；**桌面安装包只携带正式运行源码，不携带测试题和测试截图**。

整理/审计：

```powershell
python tools/repository_audit.py
python tools/clean_generated.py               # 默认只列出可清理内容
python tools/clean_generated.py --apply       # 仅删除明确列出的构建物/缓存
```

不会删除 `.env`、模型密钥、已生成视频、微调历史、数据库、用户上传课程包、数学教师提示词或 Git 提交历史。

## 6. 自动化验收与限制

- `system-ci.yml`：Windows/Linux 原生源码、数学教师/视觉导演、视频引擎非渲染测试、Docker Compose 配置。
- `frontend-screenshots.yml`：真实 Chromium 页面交互及 FFmpeg 实际编码抽取水印单帧，截图发布为 workflow artifact，不再由 CI 自动提交覆盖分支。
- `windows-desktop.yml`：原生 Windows 构建 **NSIS Setup + Portable EXE**，检查打包资源存在、不会携带测试材料和私密文件，并提供可下载的 GitHub Actions artifact。

Windows 安装程序能构建/启动界面，**不等于**已经实测了你的 Windows 本机 Docker 初始化、真实厂商 API Key、TTS 网络质量、Manim/LaTeX 的完整 60 FPS 教学视频。真实新题成片需要在实际设备和账号上做一次端到端现场验收。首次下载完整渲染依赖可能耗时、占用较多磁盘。CI 不以模拟的媒体桩视频冒充真实教学内容。

发布日期：2026-11-02。以 GitHub `main` 代码和本次运行的实际 CI 结果为准。
