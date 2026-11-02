# 微光数学 · Windows 电脑 App 1.0.8

**Windows 单平台、两文件交付。** 这是考研数学教学视频系统，包含数学教师、审稿、课堂编排、白板动画、Manim 数学公式、中文神经语音、60 FPS 视频、右上角品牌水印、视频下载和多轮微调历史 JSON 导出。

## 交付文件

GitHub Actions 的 [Windows 桌面构建](.github/workflows/windows-desktop.yml)通过后，唯一发布附件应包含：

| 文件 | 用途 |
| --- | --- |
| `WeiGuang-Math-Setup-1.0.8-x64.exe` | Windows 10/11 x64 安装包；内置 Windows 原生 Python/Manim/FFmpeg、PostgreSQL 17 和 MiKTeX 公式组件安装器 |
| `WeiGuang-Math-Source-1.0.8.zip` | 全部前端、后端、动画与教师引擎、桌面程序、构建配置、必要测试和源码清单，用于后续修改维护 |

两个文件来自同一 Git 提交。源代码压缩包包含 `release-manifest.json`，保存构建提交、安装包 SHA-256、各源码文件 SHA-256。发布包不包含测试视频、用户数据库、密钥、演示截图及无关安装版。

## Windows 原生工作方式

**不需要安装 Docker Desktop、WSL2、Ubuntu、Redis 或外部 Python 环境。** 本地使用模式由桌面程序直接启动 Windows 原生 PostgreSQL 17、Python FastAPI、Manim 和 FFmpeg。原来的 Celery/Redis 容器队列在本地模式改为单进程顺序执行，并使用 PostgreSQL 持久化任务状态。首次打开 App 时，从安装包中自动初始化 MiKTeX Portable 以及专属 PostgreSQL 数据目录；无需另行下载上述基础运行时。MiKTeX 可能为缺失的 LaTeX 宏包按需联网下载，在线 AI 与语音服务同样需要网络。

安装后打开「微光数学」→「本地视频引擎」→「启动并进入工作台」，桌面 App 将完成初始化、服务健康检查及本地登录。数据库、课程、用户视频、微调记录和加密凭据不放在程序安装目录，后续正常更新不能覆盖或删除这些用户数据。

本地服务只监听 `127.0.0.1`，由 Windows 加密的随机密钥保护登录与模型配置。应用会校验本地服务的 HMAC 身份，不会把已有账号密码作为明文交给任意网页。

## AI 平台

支持 Codex、Gemini、CodeBuddy 官方 CLI 登录与型号选择，以及各种适配协议的 API 模型。全局模型选择统一用于教师 A/B/C、课堂编排、视频文案、审核与微调。模型候选列表不代表账号实际享有权限，需用真实账号进行认证和调用测试。

**限制：** 第三方官方 CLI 不包含在本次 Python/视频依赖资源内；CLI 账号认证与可用型号取决于各供应商客户端、套餐、网络地区及官方支持。此项仍需单独完成真实 Windows 账号验收，不能因为界面有登录按钮就认定授权已成功。

## 维护与数据保护

源码包包含 `desktop/`、`backend/`、`frontend/`、`animation_engine/`、`teacher_module/`、`visual_director/`、`config/`、`tools/` 和 CI 工作流。发行脚本位于 `tools/build_source_release.py`，Windows 原生依赖预装脚本位于 `tools/stage_windows_native.ps1`。必要的回归测试题目构造器作为维护代码保留，不包含生成视频。

从 v1.0.7 Docker 版迁移时，**不会擅自删除、覆盖或自动迁移**原来的 Docker `pgdata`、`lessondata` 卷。旧数据若需要保留，必须先备份，然后通过审核过的 PostgreSQL 迁移方案将数据和媒体分别复制并验证。切勿卸载 Docker 之前删除旧卷。用户账号授权信息、视频、微调历史和密钥需要独立保护。

## 验收标准

1. 在 Windows GitHub Actions 原生构建时安装全部基础二进制依赖，并校验官方 MiKTeX 安装包 SHA-256。
2. 实际启动打包的 PostgreSQL、Python FastAPI 与公式组件，检查服务健康和依赖导入。
3. Electron 真实窗口与前端安全检查通过；唯一 NSIS EXE 和唯一完整源码 ZIP 均有大小与目录校验。
4. 最终发布前，还必须使用全新 Windows 用户环境完成一条真实数学题的完整 AI 生成、审核、配音、渲染、下载和多轮微调；**CI 通过本身不代表完成此项人工验收**。

## 视觉与教学约定

课堂白底黑字；题干置顶，核心公式随教师讲解逐步板书；长证明合理分幕，避免不必要拆分；知识点、思维引导、易错点与归纳总结有独立语义；默认 1280×720、60 帧，支持晓晓与云希语音，字幕只跟随真实口播。总结板书引用已讲过的核心知识点公式和易错点，不重复冗长完整解题。

## Windows 安全说明

Windows NSIS 内部构建尚未配置可信代码签名证书。公开发行前需签名、扫描依赖并进行供应链审核。安装程序中的 MiKTeX、Python 和 PostgreSQL 组件遵守各自开源发行许可。请勿向 GitHub 提交 API Key、密码、数据库文件或用户数据。

构建日期：2026-11-02；目标版本 1.0.8。**以对应构建工作流的实际成功状态和测试结果为准，不要把未通过验证的构建称为可交付正式版。**
