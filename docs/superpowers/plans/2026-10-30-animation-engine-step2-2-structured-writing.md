# Animation Engine 2.2 — 可信数学分段书写与短视频 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Use TDD RED → GREEN for each task.

**Goal:** Based on 2.1 real MathTex and immutable execution contracts, render a short authentic Manim MP4 showing approved mathematical parts being written in order, with blue highlight and restoration, without inventing spoken timing or math steps.

**Architecture:** A read-only, provenance-bound per-object hint explicitly names math segments and an occurrence-specific highlight index. Validation proves exact concatenation to the original immutable LaTeX and source SHA, or falls back to a single whole-formula Write. A separate Manim scene renders the prevalidated formula into a fixed region with Write, color-only highlight, and fade-back to original; outputs MP4 and an audit manifest in a temporary work directory.

**Tech Stack:** Python 3.11, Pydantic v2, Manim 0.22.1, ffmpeg, pytest, GitHub Actions; reuse 2.1 render extra and CI system dependencies.
**Spec:** docs/superpowers/specs/2026-10-30-animation-engine-phase2-design.md

## Constraints

- New branch `feature/animation-engine-v1-step2-2` from 2.1 SHA `da678ee0ebb01f23cf931c5eda6fe69045682181`, Draft PR against `feature/animation-engine-v1-step2-1`; no merges.
- Keep 2.1 plan/preview behavior; no changes to teacher content; no AI/TTS.
- White #FFFFFF, ink #1E293B, highlight #2563EB; no pen/hand/flying effects; all glyphs compiled MathTex, no plain text fallback or edit to original formula.
- Hint segments must concatenate **byte-for-byte** to selected original LaTeX; IDs/hash/speech anchor must match the true `progressive_write` action and originating board. No arbitrary substring inference; repeated identical occurrences are selected by *index*, never by text matching.
- If trusted hint absent, single whole-formula Write and highlight (when requested). If supplied hint invalid, fail loudly, never silently fallback.
- Preview animation times are explicitly `preview_only_not_audio_aligned`, not speech timestamps. One visible formula and its approved parts only; full multi-formula board, layout reflow and auto cuts belong to 2.3/2.4.
- No arbitrary untrusted TeX service; use approved lesson input, TeX restrictions, bounded scene settings. Do not recompile or recalculate the teacher solution.

## Review focus

- Hash matches but hint changes mathematics; reject.
- Duplicate LaTeX segments; exact selected occurrence is highlighted, not all matching text.
- Missing or malformed hint; fallback only if absent, with explicit provenance in manifest.
- Real initial frame contains no formula; ending frame contains entire formula; only targeted area ever becomes blue; final ink restored.
- MP4 has >1 frames, ffprobe decodes, manifests match exact original source; no faux animation/blank video/false audio timing.

### Task 1: Pure animation-cue validator and tests
**Files:** Create `animation_engine/src/animation_engine/writing_cues.py`; test `animation_engine/tests/test_writing_cues.py`.
**Interface:** `plan_math_writing(storyboard, execution, *, event_id, object_id, hint: dict|None=None) -> MathWritingPlan`; `MathWritingError`. The plan preserves render request and source speech unit, contains immutable `parts: tuple[str,...]`, `highlight_index: int|None`, `mode: segmented|whole_formula`, `hint_source: approved_explicit|safe_fallback`.
- [ ] Write tests: real `m_k_sin` data with exact original parts, provenance, no upstream mutation; missing hint = 1 part; same text duplicated selected via index; reject SHA/id/speech mismatch, reordered characters, missing/extra parts, forbidden TeX, out-of-bounds index.
- [ ] Run cloud CI RED on missing module.
- [ ] Implement pure validator with 2.1 select_math_render_request and official execution action; bind full source by SHA; reject unknown/overridden action.
- [ ] Run cloud GREEN then regression.

### Task 2: Real progressive Write, blue highlight/restore
**Files:** Create `animation_engine/src/animation_engine/writing_clip.py`; test `animation_engine/tests/test_writing_clip.py`.
**Interface:** `render_math_writing_clip(plan, *, output_mp4:Path, output_json:Path, width=1280, height=720, fps=15)->MathWritingClipResult`.
- [ ] Write real Manim integration tests for fallback and indexed segmented modes, manifest and true MP4 decode with ffprobe; check generated actual frame appearance at beginning/mid/end (without fabricated speech alignment), overflow, invalid inputs, no success outputs.
- [ ] Cloud real-render job RED.
- [ ] Render `MathTex(*parts,arg_separator="")` for explicit mapping, assert rendered submobjects map exactly 1:1; no transform of original LaTeX. Compute bbox before any Write. `Scene.play(Write(part))` sequentially; highlight only `part[index]` using color-only animation and restore; no other content or fake narration.
- [ ] Cloud real-render job GREEN and inspect complete film frames, provenance JSON.

### Task 3: CLI and genuine artifact pipeline
**Files:** Modify `animation_engine/src/animation_engine/cli.py`, `animation_engine/README.md`, `.github/workflows/animation-mathtex-step2-2.yml`; add `animation_engine/examples/sin_taylor_writing_hint.json` (curated hint with real action/hashes).
- [ ] Write CLI positive + negative tests; RED before implementation.
- [ ] Add `math-animation render-writing --storyboard ... --execution ... --event-id ... --object-id ... [--hint ...] --output ... --manifest ...`, preserve old commands.
- [ ] Real end-to-end 19-scene fixture → action ID → curated segments → real MP4 + JSON; fallback single-write video; upload artifacts.
- [ ] All teacher/director/animation engine suites GREEN on latest head; code review, Draft PR, no merges.

**Out of scope:** arbitrary semantic step generation, TTS, actual spoken timing, full video lesson, geometry animation, auto scrolling/cutting.
