# V2.6.6 渲染与增量微调技术说明（2026-11-01）

## 状态与来源

V2.6.6 原始 HEAD `9e4f47bcd6ff` 的全部测试已经通过：[真实有声编辑与性能测试](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963404)，[四种真实长视频测试](https://github.com/qichenzheng-bit/shipinyinqing/actions/runs/41268963398)。目前处于统一集成；集成后仍须重新验证。之前曾写“尚无事件级重渲染”，该描述已被最终实现替代。

## 资源缓存及正确性

- `render_cache.py`：真实 PCM、MathTex 透明字幕 PNG、完整分幕、事件片段、图像复合和转场，按语音文本、voice、speech_rate、采样率、数学来源、版本和动作参数做密钥隔离。缓存读取时校验 SHA-256、音频波形或图像透明区、原始 MP4 视频帧及对应来源。
- `edit_impact.py`：对比实际前后 JSON，不能信任 AI 自报影响范围。数学对象/布局/语音/语速变化时采取分幕或全局失效；无变化的分幕仍须通过缓存验证才可复用。
- `incremental_render.py`：从首次完整可信分幕提取事件片段，后续仅对来源、精确帧数、事件 ID、入场板书状态等均一致的事件复用。状态无法确认时整幕重渲染；视频失败不得覆盖上一轮成功的 `latest.mp4`。
- `sparse_caption_mux.py`：按真实字幕边界帧叠加 Manim MathTex，尽量只做一次 FFmpeg 混流；失败时退回原 FFV1 透明字幕带方案，不能省掉真实配音或字幕。
- 安全 H.264 视频拼接只有在编码兼容、帧数准确且来源可信时才使用 bitstream copy，否则回退重编码。

## 本次实测（原始 HEAD）

- 相同修改任务无缓存 **181 秒**，有缓存 **74 秒**，加速 **2.45 倍**、降低约 **59.1%**；不是普遍的速度保证。
- 完整有声视频 5,940 帧、两轮真实编辑、两个分幕缓存命中、54 个真实语音片段命中、54 个字幕图像命中；事件级视频命中与重新拼接已通过验证。
- 真正 Manim/MathTex 1280×720、30 FPS 长视频：嵌套积分 1110 帧、七步矩阵 1206 帧、归纳法证明 1045 帧、三种分类情况证明 1121 帧。

## 语音体验同步

语音合同支持 `zh-CN-YunxiNeural` 与 `zh-CN-XiaoxiaoNeural`；课程可选 `speech_rate`，缺省 `+1%`，相对原 `-4%` 的设置提高约 5.2% 名义播速。**语音时长以 Edge 实际 PCM 为准**，更换声音或速度时重新推导动画与字幕时间码。对应独立双音色真实验收见 [集成验收记录](V2_6_INTEGRATION_2026-11-01.md)。

```bash
math-animation render-spoken --spoken work/package/spoken_classroom.json --output work/lesson.mp4 --manifest work/lesson.json --srt work/lesson.srt --adaptive --fps 30 --cache-dir work/resource-cache
```

本工程假设来源已由教师审核；不能仅依赖演示自动证明任何新数学证明正确，也不假称已接入无需人工审查的 AI 自动解题。
