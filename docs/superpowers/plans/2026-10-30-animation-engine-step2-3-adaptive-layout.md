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

Transition preview: math-animation render-layout-transition --storyboard storyboard.json --execution execution.json --from-event-id PREVIOUS_EVENT_ID --to-event-id NEXT_EVENT_ID --output transition.mp4 --manifest transition.json

The two event IDs must be adjacent and both fit safely; the code rejects survivor tween collisions. Timing is preview-only, never speech-aligned.

## Limitations

This is Stage 2.3's initial implementation, not a completed classroom movie. No long-expression semantic multiline breaking, no full lesson-length tween/composition system (only a real two-scene MP4 transition preview), no full Chinese header or spoken subtitles, no audio or automatic cuts. move_at_action_boundary is now implemented in the explicit two-scene render-layout-transition preview; it is not yet wired to a full audio timeline. Stage 2.4 owns scrolling and cuts. Real glyph preview is for offline trusted mathematical content; TeX must be sandboxed before any public service.

## Validation

New offline geometry tests, source matching and explicit overflow tests; true MathTex PNG and actual Manim MP4 tests under the render extra; a dedicated GitHub Actions workflow saves real visual evidence. CI alone is not human visual acceptance.
