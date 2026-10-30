"""Three-stage AI workflow with fail-closed structural checks and review gates."""
from __future__ import annotations
import hashlib
import json
from importlib.resources import files
from .models import (
    TeacherInput, Understanding, TeachingPlan, LessonDraft, TeachingPackage,
    ValidationReport,
)
from .provider import JsonModel
from .validator import Collector, check_input_sources, check_understanding, check_plan, check_lesson, compile_report

PROMPT_VERSION = "1.1"


class PipelineValidationError(RuntimeError):
    def __init__(self, stage: str, report: ValidationReport):
        self.stage = stage
        self.report = report
        super().__init__(f"Math teacher stage {stage} stopped: {report.status}")


class MathTeacherPipeline:
    """Only builds a TeachingPackage. No TTS, timing, Manim, frontend or backend."""
    def __init__(self, provider: JsonModel):
        self.provider = provider

    @staticmethod
    def _prompt(name: str) -> str:
        return files("math_teacher").joinpath("prompts", name).read_text(encoding="utf-8")

    def _generate(self, stage: str, name: str, payload: dict, contract):
        system = self._prompt("global.md") + "\n\n" + self._prompt(name)
        return self.provider.generate(
            stage=stage, system=system,
            user_json=json.dumps(payload, ensure_ascii=False, sort_keys=True), schema=contract,
        )

    def run(self, source: TeacherInput, *, allow_needs_review: bool = False) -> TeachingPackage:
        source = source.with_sources()
        collector = Collector()
        if not source.problem.strip() or not source.reference_solution.strip():
            collector.add("input", "EMPTY_REQUIRED_INPUT", "Question and answer analysis are both required")
            raise PipelineValidationError("input", compile_report(collector, []))
        src_ids = [x.source_id for x in source.problem_segments + source.solution_segments]
        if len(set(src_ids)) != len(src_ids) or any(not s.strip() for s in src_ids):
            collector.add("input", "INVALID_SOURCE_IDS", "Source IDs must be unique and nonempty")
            raise PipelineValidationError("input", compile_report(collector, []))
        check_input_sources(source, collector)
        self._gate("input", collector, [], allow_needs_review)
        digest = hashlib.sha256(json.dumps(source.model_dump(mode="json"),
            sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        a = self._generate("A", "a_understanding.md", {"source": source.model_dump(mode="json")}, Understanding)
        checks = check_understanding(source, a, collector)
        self._gate("A", collector, checks, allow_needs_review)

        b = self._generate("B", "b_planning.md", {
            "source": source.model_dump(mode="json"), "understanding": a.model_dump(mode="json"),
            "math_verifications": [v.model_dump(mode="json") for v in checks],
        }, TeachingPlan)
        check_plan(a, b, collector)
        self._gate("B", collector, checks, allow_needs_review)

        d = self._generate("C", "c_narration.md", {
            "source": source.model_dump(mode="json"), "understanding": a.model_dump(mode="json"),
            "plan": b.model_dump(mode="json"),
        }, LessonDraft)
        subtitles = check_lesson(a, b, d, collector, source=source)
        report = compile_report(collector, checks)
        self._gate("C", collector, checks, allow_needs_review)
        package = TeachingPackage(
            schema_version="1.0", input_sha256=digest,
            prompt_versions={"global": PROMPT_VERSION, "A": PROMPT_VERSION, "B": PROMPT_VERSION, "C": PROMPT_VERSION},
            source=source, understanding=a, plan=b, lesson=d, subtitles=subtitles, validation=report,
        )
        frozen = package.model_dump(mode="json", exclude={"validated_content_sha256"})
        seal = hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        return package.model_copy(update={"validated_content_sha256": seal})

    @staticmethod
    def _gate(stage: str, collector: Collector, checks, allow_needs_review: bool):
        report = compile_report(collector, checks)
        if report.status == "blocked" or (report.status == "needs_review" and not allow_needs_review):
            raise PipelineValidationError(stage, report)
