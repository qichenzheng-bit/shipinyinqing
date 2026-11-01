# Animation Engine V1.0 — Step 1 Implementation Plan

> For agentic workers: use TDD (failing test → implementation → complete regression → review) for this scoped step. Future animation/rendering steps have separate plans.

**Goal:** Turn the existing `StoryboardPlan v1.0` into a deterministic, validated animation execution plan without calling Manim, audio, TTS, or AI.

**Architecture:** Install `visual_director` as the contract provider; use its strict `StoryboardPlan` model as the sole input. The new `animation_engine` package maintains one object identity registry, checks every action's state transition, and reconciles each scene with the director's visible/archived snapshots. Emit typed JSON with scene-level provenance, transitions, state digests, and semantic anchors only.

**Tech stack:** Python 3.11; Pydantic v2; pytest; GitHub Actions. No Manim dependencies in Step 1.

**Design reference:** Previously approved "数学动画执行模块 V1.0：事件驱动 Manim 引擎设计草案" (2026-10-30), sections 4–5 and acceptance step 1.

## Constraints
- Implement only input contract, action ordering, object lifecycle, scene snapshots, and JSON CLI.
- No new math steps or invented coordinates; never infer second-level time.
- Do not change teacher_module or visual_director's production contract.
- Separate branch from pending PR #3; no merging.
- Stable `action_id`, `event_id`, `object_id`, `speech_unit_id`, and `source_step_ids`; provenance must survive archival/restoration.

## Scope tests and review focus
1. Real 19-scene example from `visual_director` compiles deterministically; header-only highlight doesn't create a formula.
2. Missing regions, duplicate actions, unknown speech anchors, incorrect final visible/archived snapshot → explicit execution errors, never silent correction.
3. Archived formula can be restored and highlighted; scratch → board migration remains the same object.
4. Reuse of object ID with a different LaTeX/provenance → reject; future objects never visible early.
5. Output has stable SHA256 and contains semantic anchors only (no synthetic durations).

### Task 1: Package + contract validation
- [ ] Write tests importing `animation_engine.build_execution_plan` and parsing a real `StoryboardPlan`.
- [ ] Run independent CI and inspect the expected RED failure.
- [ ] Define `animation_engine/pyproject.toml`, `models.py`, `planner.py`, `__init__.py`.
- [ ] Enforce official Pydantic `StoryboardPlan`, scene IDs, action IDs, speech anchors, region ownership, and immutable provenance.

### Task 2: Deterministic state machine + CLI
- [ ] Tests for write, highlight, archive, restore, migrate, remove, and snapshot failure.
- [ ] Implement scene-by-scene transitions with before/after states, regions, and stable hash of terminal state.
- [ ] CLI `math-animation plan storyboard.json --output execution.json`; no video rendering yet.
- [ ] Repeat identical input, assert identical execution JSON and no mutation to input.

### Task 3: Cloud regression and handoff
- [ ] Add dedicated workflow running teacher, director, and animation-engine tests.
- [ ] Use the real teacher fixture to generate storyboard via visual-director CLI, then animation-engine CLI.
- [ ] Confirm complete suite success and log exact counts.
- [ ] Open draft PR against `fix/v1-review-20261029`, preserve old unmerged PRs, do not merge.

**Not included:** MathTex, geometry rendering, caption layout, video export, actual clock timing, real audio, local cache persistence, media pipeline.
