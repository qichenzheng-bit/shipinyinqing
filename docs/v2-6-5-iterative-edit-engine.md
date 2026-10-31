# V2.6.5 无界面连续微调引擎

本阶段仅包含引擎和 CLI，不包含 GUI，也不提供用户侧新旧视频对比。

## 原则

- 可以使用任意语言提出任意数量的修改要求。AI 理解请求的语义，不依赖预定义的用户指令关键词。
- 每轮修改必须从最新已生成且通过验证的视频源开始；不满意就继续修改，满意后结束。
- 只展示/导出最新视频：session/latest.mp4。旧素材仅在系统内部用于恢复、追溯，不需要用户看旧视频。
- 只提供一个用户训练数据导出格式：完整 JSON，原样保存用户每一轮指令、多个子要求、操作前后内容、失败记录、模型身份及满意反馈。
- 暂不以节省 token 或缓存命中率为目标。源校验、真实 TTS、MathTex、真实视频优先。

## 四个引擎模块

1. **2.6.5.1 会话与版本基础**：V2.6.4 已验收视频初始化；不可变来源快照；写入锁；当前最新视频原子更新。
2. **2.6.5.2 自然语言与多要求**：可插拔的 AI 回调或显式配置的 OpenAI-compatible 模型；每个独立要求对应一个或多个源操作；模型获得最新视频时间码、实际字幕和之前所有用户反馈。
3. **2.6.5.3 编辑与真实媒体生成**：对源 JSON 字段进行任意合法更新，再检查数学来源、图形生命周期、跨幕记忆、完整口播覆盖；成功后实际生成 Edge TTS + Manim MathTex 视频，失败不污染 latest.mp4。
4. **2.6.5.4 反馈、验收、单一 JSON 导出**：用户不满意继续同一会话，满意标记结束；包含成功与失败的所有真实指令和逐项结果；一键导出 JSON。

## 命令行使用

从上一阶段已经真实渲染且拥有审计清单的教学源建立会话：

    math-animation edit-start --package spoken-evidence/triangle --movie spoken-evidence/triangle/spoken_teaching.mp4 --manifest spoken-evidence/triangle/movie_manifest.json --session work/edit-session --fps 30

方式一：接受其他 AI 生成并经过审查的结构化多要求编辑计划：

    math-animation edit-apply --session work/edit-session --instruction-file instruction.txt --plan edit_plan.json

方式二：明确授权并配置外部模型进行自然语言理解：

    math-animation edit-apply --session work/edit-session --instruction-file instruction.txt --ai-config local_model_config.json

模型配置 local_model_config.json 示例：

    {
      "kind": "openai_compatible",
      "model": "your-model-id",
      "endpoint": "https://your-provider.example/v1/chat/completions",
      "key_environment": "EDIT_MODEL_API_KEY"
    }

API key 只从用户自设环境变量读取，不写入仓库、日志或 JSON 导出。实际连接第三方模型会把当前源 JSON、字幕、时间码和修改历史发送给该模型；必须先取得用户授权。没有密钥时不会声称已完成真实在线 AI 理解。

多要求 edit_plan.json 示例：

    {
      "schema_version": "1.0",
      "model": "teacher-approved-agent",
      "requirements": [
        {"id":"r1","instruction":"第一幕更自然","target":"introduce_triangle/e_intro","operation_ids":["p1"]},
        {"id":"r2","instruction":"第二幕更加清楚","target":"introduce_triangle/e_angle","operation_ids":["p2"]}
      ],
      "operations": [
        {"id":"p1","file":"spoken_classroom.json","pointer":"/events/0/spans/0/parts/0/value","action":"set","value":"我们先整理这道题给出的条件。"},
        {"id":"p2","file":"spoken_classroom.json","pointer":"/events/1/spans/0/parts/0/value","action":"set","value":"观察直角顶点，两条直角边相互垂直。"}
      ]
    }

每轮播放最新结果，若仍不满意：

    math-animation edit-feedback --session work/edit-session --text "第一幕已经满意，第二幕再详细一些"

接着再次 edit-apply；最终满意：

    math-animation edit-feedback --session work/edit-session --text "这次满意了" --satisfied

唯一的训练数据 JSON 导出：

    math-animation edit-export --session work/edit-session --output work/video_edit_history.json

**最新视频始终是 work/edit-session/latest.mp4，最新字幕为 latest.srt。**

## 安全与数学质量

- AI 编辑计划是未验证数据，不允许运行其返回的任意 shell/Python 命令。只修改当前工程来源目录中的合法 JSON 文件路径，禁止路径逃逸、符号链接和源代码注入。
- 真正改变数学证明、源计算或引用关系时，必须重新建立合法来源合同，并通过额外受信任的数学审查。CLI 支持显式的 --math-reviewer trusted.module:function；无此审核则拒绝涉及数学源文件的操作。单凭 AI 声称正确不算证明。
- AI 能理解的具体语言和视频编辑效果取决于所连接模型及对应来源能力。无模型凭据时可使用外部生成的多要求计划，不能宣称已经完成真实无限语言模型测试。
- 用户希望保留云希、增加晓晓音色和加快约 5% 的需求另记在 Issue #29，不在本阶段悄悄改变。
- 单元测试采用明示的 mock 视频，只验证调度、覆盖和失败保护；另有真实 Edge TTS/Manim/MathTex 端到端测试，连续执行两轮编辑并用 ffprobe 核验有声视频。

## 验收

- 一轮同时提交两条修改，且两个操作都必须成功。
- 第二轮读取第一轮的最新源，保留已经认可的第一幕，只改第二幕。
- 每轮要求、AI 输出计划、修改前后与反馈完整保存在 JSON。
- 真实 MP4 最终可播放、含音频、口播完整、数学字幕由真正 MathTex 渲染。
- 用户只需查看最新 MP4，无 UI 或版本对比要求。
