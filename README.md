# 考研数学教学视频引擎（shipinyinqing）

这是按 **教学内容 → 视觉导演 → 动画执行** 划分职责的考研数学教学视频工程。当前已经有可运行的教师事件/分镜合同、MathTex 数学渲染、真实 Manim 视频及可追溯的页面布局和预览验证；旧版目录与合同仍在，不能因为某段示范视频通过就声称所有题型或 AI 自动教学已完成。

## 用户确认的简单题课堂模式

- 白底、题干居中固定，**数学表达式与题干数学字号匹配**，数学解析统一黑色；答案不加框。
- 思维引导蓝色、核心知识点紫色、易错点红色、归纳总结绿色；标题和正文使用固定字号，讲到相应知识才作为板书写出，不是题干下面一直悬浮的提示卡。
- 黑板**只追加书写**，每个知识点与相应公式写到哪里就保留到哪里，后面的知识点和公式接着往下写；禁止每一步淡出、移动旧公式、滚动回排。
- 只有下一个**完整教师事件**不能放下时才执行一次整板擦除，固定题干不擦；如需要早先计算结果，擦后依据原 MathTex 和来源重新书写。不能中途拆断复杂分式或矩阵。
- 讲解面向考研基础较弱和中等水平学生，完整解释方法、依据和必要计算，不机械地增加细碎废话。长证明/图形/矩阵仍需专门版式，不强制套简单题模板。
- LaTeX 显示、未来 TTS 发音映射、真实字幕三条数据独立。当前验收 MP4 仍为无音频演示，未实现真实口播—板书—字幕时间码对齐；不接入在线 AI 生成教学内容。

### 运行与示范

`animation_engine/src/animation_engine/classroom_policy.py` 是简单题标准课堂配置的统一入口。带教师审核教学提示 `--classroom-cues` 且未显式指定 `--policy` 时，`plan-longboard` / `render-longboard` 默认使用该持续板书模式；复杂教学可显式传入专业版式配置。

此前的五阶泰勒极限题现已从19次机械拆分重构为5个完整教学环节，并补上遗漏的高阶乘法推导。此次另选**一阶线性微分方程初值问题**作为全新题型验收：

```bash
python animation_engine/tools/build_complete_ode_lesson.py --output ode-demo

math-animation plan-longboard \
  --storyboard ode-demo/storyboard.json \
  --execution ode-demo/execution.json \
  --classroom-cues ode-demo/teacher_approved_cues.json \
  --policy ode-demo/page_policy.json \
  --output ode-demo/board_pages.json

math-animation render-longboard \
  --storyboard ode-demo/storyboard.json \
  --execution ode-demo/execution.json \
  --classroom-cues ode-demo/teacher_approved_cues.json \
  --policy ode-demo/page_policy.json \
  --output ode-demo/classroom.mp4 \
  --manifest ode-demo/video_manifest.json --fps 30
```

CI workflow: `.github/workflows/classroom-complete-units-fresh-ode.yml`，包括旧泰勒内容重构回归、新微分方程的 SymPy 独立验算、所有动画模块回归、真实 MathTex 排版、逐页板书与 MP4 关键帧。教学编译器 `classroom_teaching_units.py` 支持一个完整教学环节连续写多条公式，不再强制每条公式变成一个独立讲解。先安装 `visual_director`、`animation_engine[render,test]` 及对应系统 LaTeX/Manim/FFmpeg 依赖。

详见 `animation_engine/README.md` 和 `docs/superpowers/plans/`；所有专项 PR 均先保持 Draft，不自动合并 `main`。