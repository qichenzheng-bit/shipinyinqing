# 考研数学教学视频引擎

**现行版本：V2.6 统一集成候选（2026-11-01）。** 项目按教师审核教学内容、视觉导演、真实动画渲染三个工程组织。V2.5.1—V2.6.6 的核心模块已有分支级真实视频及 CI 验收记录，最终发布以 main 合并后的测试为准。

## 功能进度

| 阶段 | 已实现 |
| --- | --- |
| V2.5.1—2.5.4 | 多项积分、矩阵/行列式、长证明/分类讨论、函数图像与积分区域 |
| V2.6.1—2.6.3 | 统一课程衔接、自适应板书、图形保留恢复、跨幕数学记忆 |
| V2.6.4 | 实际 Edge 神经语音、真实 MathTex、口播/板书/字幕逐动作同步 |
| V2.6.5 | 多要求自然语言微调、连续编辑、失败回退、最新 MP4、单一 JSON 导出 |
| V2.6.6 | PCM/字幕缓存、分幕和来源校验的事件级缓存、依赖失效与安全回退 |

教学约束：白底、固定居中题干、黑色数学解析、蓝色思维引导、紫色知识点、红色易错点、绿色总结；不用答案框。真实 MathTex 不准随意替换，短公式可并排，已写板书保留直到安全擦板；字幕只根据实际教师口播显示，数学读音与屏显 LaTeX 严格隔离。数学内容须先经教师审核，不假称引擎已经实现自动解题。

## 语音选择与约快 5% 的默认播速

审核后的 `spoken_classroom.json` 中，`voice` 可选 `zh-CN-YunxiNeural`（保留云希）或 `zh-CN-XiaoxiaoNeural`（晓晓）。`speech_rate` 是可选字段：

```json
{"voice":"zh-CN-YunxiNeural","speech_rate":"+1%"}
```

旧版实际 TTS 使用 `-4%`。当前默认 `+1%`，名义播速相比旧值提高约 5.2%；可显式设为 `-4%` 使用原速。按 PCM 实际音频时长重新生成整条音画时间轴，而非对旧视频变速。已审核的合法速率范围为 `-30%` 至 `+30%`，带符号。音色/速率均进入缓存键及最终视频清单，改变时不错误复用旧声画。

## 运行示例

依赖真实 Manim、LaTeX、dvisvgm、FFmpeg、中文字体及可连接的 Edge TTS。

```bash
python -m pip install -e './teacher_module[test]' -e './visual_director[test]' -e './animation_engine[render,test,speech]'
python animation_engine/tools/build_spoken_triangle.py --output demo
math-animation plan-spoken --spoken demo/spoken_classroom.json --output demo/plan.json --adaptive
math-animation render-spoken --spoken demo/spoken_classroom.json --output demo/lesson.mp4 --manifest demo/lesson.json --srt demo/lesson.srt --adaptive --fps 30 --cache-dir demo/resource-cache
```

微调引擎支持 `edit-start`、`edit-apply`、`edit-feedback`、`edit-export`；当前没有用户操作界面，开放式 AI 计划器必须显式配置并通过数学来源审查。无审核 TeX 不应在没有低权限沙箱、CPU/内存/超时限制的公网环境直接执行。

## 口播与真实绘图同步（2026-11-01 追加）

绘图类课堂要求老师说到哪个图元，就在同一口播动作中真实绘制该图元。完整三角形必须在声明画出完整图形的教学事件内形成；不得让图元在语音开头匆忙出现，余下长时间只播放音频。跨幕结论承接保留数学来源，不机械重复整段解说。以真实 Manim/MathTex 动画、PCM、字幕和 `diagram_reveal_timing` 检查为准。详见 [口播与可视动作同步规范](docs/V2_6_SPOKEN_VISUAL_SYNC_2026-11-01.md)。

## 真实验收

- [V2.6.6 原始 HEAD 有声编辑和性能测试](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963404)：相同编辑任务冷缓存 181 秒、热缓存 74 秒，提速 2.45 倍；仅代表该测试任务。
- [V2.6.6 原始 HEAD 跨题型长视频](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963398)：积分、矩阵、长证明及分类证明。
- [V2.6 统一集成记录](docs/V2_6_INTEGRATION_2026-11-01.md)；[增量渲染说明](docs/v2-6-6-efficient-incremental-render.md)。

历史开发文档保留在 `animation_engine/README.md` 和 `docs/superpowers/plans/`。其中历史“未实现真实配音”等语句仅代表当时阶段，不再代表 V2.6 当前能力。
