# Animation Engine V1.0 - Stage 2.3 implementation notes

Branch: feature/animation-engine-v1-step2-3, stacked on Stage 2.2. Do not merge automatically.

## Implemented

- Full StoryboardPlan and ExecutionPlan cross-validation; immutable mathematics and provenance.
- Real Manim MathTex dimensions drive a separate per-scene layout overlay.
- Fixed header/caption safe zones, two-column placement with safe scratch expansion.
- Retain previous object positions where possible; record appearance, hold and movement proposals.
- When possible, align first equal signs from measured glyph positions.
- Bound scale to 90%-100%, verify pixel boundaries and collision.
- Explicit cut_required result with empty placements when content cannot safely fit.
- math-animation layout-board generates JSON; with event-id, also genuine multi-formula PNG and manifest.

## Commands

First generate storyboard.json and execution.json from existing CLI.

Plan: math-animation layout-board --storyboard storyboard.json --execution execution.json --output layout.json

Render: math-animation layout-board --storyboard storyboard.json --execution execution.json --event-id REAL_EVENT_ID --output board.png --manifest board.json

Choose a real event_id with status ready and visible mathematical objects.

## Limitations

This is Stage 2.3's initial implementation, not a completed classroom movie. No long-expression semantic multiline breaking, no actual tween video for existing objects, no full Chinese header or spoken subtitles, no audio or automatic cuts. move_at_action_boundary is planning metadata only. Stage 2.4 owns scrolling and cuts. Real glyph preview is for offline trusted mathematical content; TeX must be sandboxed before any public service.

## Validation

New offline geometry tests, source matching and explicit overflow tests; true MathTex PNG test under the render extra; a dedicated GitHub Actions workflow saves real visual evidence. CI alone is not human visual acceptance.
