# 微光数学 Web 后端 V1

适用于 Windows + WSL2 / Docker Desktop 开发，Linux 服务器可使用同一份 Docker Compose。

## 启动

1. 将根目录 `.env.example` 复制为 `.env`，设置安全的 `POSTGRES_PASSWORD` 和 `WEIGUANG_API_TOKEN`。
2. 如需 AI 数学教师，设置 `WEIGUANG_TEACHER_ENABLED=1`、`MATH_TEACHER_MODEL`、`MATH_TEACHER_API_KEY`（Worker 使用密钥，API 只读取功能开关）。
3. 如需真实多轮微调，将 `config/edit_ai.example.json` 复制为 `config/edit_ai.json`，指定支持 HTTPS 的模型服务和模型名；设置 `WEIGUANG_EDIT_AI_ENABLED=1`、`WEIGUANG_EDIT_AI_KEY`。真实审核回调需提供可信 `module:function`，未提供时 V2.7 审核可能拒绝，不允许自动假通过。
4. 在项目根目录运行 `docker compose up --build -d`。默认只监听 `127.0.0.1:8000`，避免未经 TLS 的公网 API。使用服务端 Nginx + HTTPS 接入公网。
5. 浏览器打开 `http://127.0.0.1:8000/`，输入 `WEIGUANG_API_TOKEN` 登录。

```powershell
Copy-Item .env.example .env
Copy-Item config/edit_ai.example.json config/edit_ai.json
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

## 主要流程

创建题目 → AI 数学教师 A/B/C → 人工审核 → AI 课堂编排候选 → 人工审核 → 编译 V2.7 严格课程包 → 完整讲稿审核 → Celery + Manim + TTS + FFmpeg 制作 → MP4 下载 / 继续微调。

没有模型 API 密钥时，允许导入**来源与原题严格匹配**的受审课程 ZIP，进行讲稿审核和视频生产；不能凭空生成教学解答。

视频导出采用按任务 ID 独立文件路径；来源修订、AI 变更、渲染失败不能覆盖旧版成功 MP4。所有微调历史按 session 索引后通过**一个** JSON 接口导出。

## 验收命令

在已安装测试依赖的项目中：

```powershell
python -m pytest backend/tests -q
python backend/tests/capture_pages.py
```

真实媒体验收需要 Windows / Linux 设备具备 FFmpeg、LaTeX、dvisvgm、Manim、中文字体、TTS 网络连接、合适的视频编码器和真实模型密钥。CI 使用刻意标记的媒体测试桩，仅证明非渲染接口闭环；**不能将测试桩 MP4 冒充真实教学视频**。

## 安全与备份

- `config/edit_ai.json`、`.env` 绝不提交 Git；用服务器密钥管理或受控文件权限管理。
- Web 登录会话使用 HttpOnly SameSite Cookie，服务器要求真实密钥；在公网必须使用 HTTPS。
- 数据卷 `pgdata`、`lessondata`、`redisdata` 应定期备份。只备份 MP4 无法恢复微调历史。
- 完整的课程包和脚本有数学来源及显式审批；编译完成不能替代数学教师人工判断。
