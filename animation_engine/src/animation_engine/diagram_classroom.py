"""V2.5.4 verified graphical teaching: source data, labels and stage reveals.

Every dot, line and curve is copied from a frozen StoryboardPlan diagram.
Only reviewed, source-bound curve-to-curve regions are supported initially.
This module does not infer plotted functions, geometric properties or areas.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Any

from visual_director.models import StoryboardPlan
from .models import ExecutionPlan
from .planner import build_execution_plan
from .longboard_plan import LongboardError
from .mathtex_renderer import validate_math_latex


DIAGRAM_PANEL = {"x":680, "y":202, "w":480, "h":358}
DIAGRAM_FORMULA_X = 110
DIAGRAM_FORMULA_W = 485
SUPPORTED_KINDS = frozenset({
    "function_graph", "integration_region", "geometry_proof"
})
STAGE_ORDERS = frozenset({"diagram_then_math","math_then_diagram"})


@dataclass(frozen=True)
class DiagramContract:
    kind: str
    source_event_id: str
    objects: dict[str,dict]
    stages: dict[str,dict]
    ordered_ids: tuple[str,...]
    source_sha256: str

    def for_event(self, event_id: str) -> dict:
        return self.stages[event_id]

    def public_manifest(self) -> dict:
        return {
            "kind":self.kind, "source_event_id":self.source_event_id,
            "object_count":len(self.objects),
            "ordered_ids":list(self.ordered_ids),
            "source_verified":True,
            "label_source_verified":True,
            "staged_reveal_not_inferred":True,
            "mathematical_truth_status":"teacher_reviewed",
            "panel":dict(DIAGRAM_PANEL),
        }


def _line_segment_intersects_label(a, b, rect) -> bool:
    from visual_director.geometry import _segment_intersects_rect
    return _segment_intersects_rect(a,b,rect,margin=.005)


def checked_diagram_classroom(payload: Any, storyboard, execution) -> DiagramContract:
    board=StoryboardPlan.model_validate(storyboard)
    plan=ExecutionPlan.model_validate(execution)
    if plan.model_dump(mode="json")!=build_execution_plan(board).model_dump(mode="json"):
        raise LongboardError("DIAGRAM_EXECUTION_SOURCE_MISMATCH")
    fields={
        "schema_version","mode","teacher_reviewed","kind",
        "source_storyboard_sha256","source_event_id","filled_regions","stages"
    }
    if (not isinstance(payload,dict) or set(payload)!=fields
            or payload["schema_version"]!="1.0"
            or payload["mode"]!="verified_diagram_classroom"
            or payload["teacher_reviewed"] is not True
            or payload["kind"] not in SUPPORTED_KINDS):
        raise LongboardError("DIAGRAM_INVALID_MANIFEST")
    if payload["source_storyboard_sha256"]!=plan.source_storyboard_sha256:
        raise LongboardError("DIAGRAM_SOURCE_HASH")
    scenes=board.scenes
    if not scenes or payload["source_event_id"]!=scenes[0].event_id:
        raise LongboardError("DIAGRAM_SOURCE_EVENT")
    diagram=scenes[0].diagram
    if diagram is None or scenes[0].layout!="diagram_split":
        raise LongboardError("DIAGRAM_FROZEN_SOURCE_REQUIRED")
    if any(scene.diagram is not None for scene in scenes[1:]):
        raise LongboardError("DIAGRAM_SINGLE_SOURCE_PANEL_ONLY")
    objects={}
    def insert(ident,kind,attrs):
        if not isinstance(ident,str) or not ident or ident in objects:
            raise LongboardError("DIAGRAM_DUPLICATE_OBJECT")
        objects[ident]={"kind":kind,**attrs}
    points={}
    for p in diagram.points:
        if p.id in points:
            raise LongboardError("DIAGRAM_DUPLICATE_POINT")
        points[p.id]=(p.x,p.y)
        if not (.035<=p.x<=.965 and .035<=p.y<=.965):
            raise LongboardError("DIAGRAM_POINT_OUT_OF_SAFE_PANEL")
        insert(p.id,"point",{"x":p.x,"y":p.y})
        if p.label:
            validate_math_latex(p.label)
    for line in diagram.lines:
        if line.start not in points or line.end not in points:
            raise LongboardError("DIAGRAM_LINE_UNKNOWN_POINT")
        if hypot(*(a-b for a,b in zip(points[line.start],points[line.end])))<.012:
            raise LongboardError("DIAGRAM_DEGENERATE_LINE")
        insert(line.id,"line",{
            "start":line.start,"end":line.end,"dashed":line.dashed
        })
    curves={}
    for curve in diagram.curves:
        pts=[tuple(pair) for pair in curve.points]
        if (len(pts)<9 or len(pts)>200
                or any(not all(isfinite(v) and .02<=v<=.98 for v in xy)
                       for xy in pts)
                or any(hypot(x2-x1,y2-y1)<.001
                       for (x1,y1),(x2,y2) in zip(pts,pts[1:]))):
            raise LongboardError("DIAGRAM_BAD_CURVE_SAMPLES")
        curves[curve.id]=pts
        insert(curve.id,"curve",{"points":[list(p) for p in pts]})
    for label in diagram.labels:
        if label.point_id not in points:
            raise LongboardError("DIAGRAM_UNKNOWN_LABEL_POINT")
        source=next(p.label for p in diagram.points if p.id==label.point_id)
        if label.text_latex!=source:
            raise LongboardError("DIAGRAM_LABEL_SOURCE_MUTATION")
        if (min(label.x,label.y,label.w,label.h)<0 or
                label.x+label.w>.985 or label.y+label.h>.985):
            raise LongboardError("DIAGRAM_LABEL_OUT_OF_PANEL")
        for line in diagram.lines:
            if _line_segment_intersects_label(
                points[line.start],points[line.end],
                (label.x,label.y,label.w,label.h)
            ):
                raise LongboardError("DIAGRAM_LABEL_INTERSECTS_LINE")
        for curve in curves.values():
            if any(_line_segment_intersects_label(
                    a,b,(label.x,label.y,label.w,label.h))
                   for a,b in zip(curve,curve[1:])):
                raise LongboardError("DIAGRAM_LABEL_INTERSECTS_CURVE")
        insert("label:"+label.point_id,"label",{
            "point_id":label.point_id,"latex":label.text_latex,
            "x":label.x,"y":label.y,"w":label.w,"h":label.h
        })
    regions=payload["filled_regions"]
    if not isinstance(regions,list) or len(regions)>3:
        raise LongboardError("DIAGRAM_BAD_FILLED_REGIONS")
    for reg in regions:
        if (not isinstance(reg,dict) or set(reg)!={
                "id","upper_curve_id","lower_curve_id"}):
            raise LongboardError("DIAGRAM_REGION_FIELDS")
        upper=curves.get(reg["upper_curve_id"])
        lower=curves.get(reg["lower_curve_id"])
        if not upper or not lower or len(upper)!=len(lower):
            raise LongboardError("DIAGRAM_REGION_NEEDS_TWO_SOURCE_CURVES")
        if any(abs(a[0]-b[0])>1e-7 for a,b in zip(upper,lower)):
            raise LongboardError("DIAGRAM_REGION_SAMPLE_X_MISMATCH")
        if any(upper[i+1][0]<=upper[i][0] for i in range(len(upper)-1)):
            raise LongboardError("DIAGRAM_REGION_REVERSED_X")
        if (max(abs(upper[i][1]-lower[i][1])
                for i in (0,len(upper)-1))>1e-7):
            raise LongboardError("DIAGRAM_REGION_OPEN_BOUNDARY")
        if any(a[1]>b[1]+1e-8 for a,b in zip(upper,lower)):
            raise LongboardError("DIAGRAM_REGION_UPPER_BELOW_LOWER")
        if max(b[1]-a[1] for a,b in zip(upper,lower))<.01:
            raise LongboardError("DIAGRAM_DEGENERATE_REGION")
        insert(reg["id"],"region",{
            "upper_curve_id":reg["upper_curve_id"],
            "lower_curve_id":reg["lower_curve_id"],
            "boundary":[list(p) for p in (upper+list(reversed(lower)))]
        })
    if payload["kind"]=="integration_region" and not regions:
        raise LongboardError("DIAGRAM_INTEGRATION_REGION_REQUIRED")
    if payload["kind"]!="integration_region" and regions:
        raise LongboardError("DIAGRAM_REGION_KIND_MISMATCH")
    stages=payload["stages"]
    if (not isinstance(stages,list) or len(stages)!=len(scenes)
            or len(stages)>20):
        raise LongboardError("DIAGRAM_STAGE_COVERAGE")
    shown=set()
    ordered=[]
    checked={}
    for scene,row in zip(scenes,stages):
        if (not isinstance(row,dict) or set(row)!={"event_id","reveal_ids","order"}
                or row["event_id"]!=scene.event_id
                or row["order"] not in STAGE_ORDERS):
            raise LongboardError("DIAGRAM_STAGE_ORDER")
        ids=row["reveal_ids"]
        if (not isinstance(ids,list)
                or any(type(ident) is not str or ident not in objects
                       for ident in ids)
                or len(ids)!=len(set(ids))):
            raise LongboardError("DIAGRAM_REVEAL_UNKNOWN_OBJECT")
        for ident in ids:
            if ident in shown:
                raise LongboardError("DIAGRAM_DUPLICATE_REVEAL")
            obj=objects[ident]
            if obj["kind"]=="label":
                if obj["point_id"] not in shown and obj["point_id"] not in ids[:ids.index(ident)]:
                    raise LongboardError("DIAGRAM_LABEL_BEFORE_POINT")
            if obj["kind"]=="region":
                for ref in (obj["upper_curve_id"],obj["lower_curve_id"]):
                    if ref not in shown and ref not in ids[:ids.index(ident)]:
                        raise LongboardError("DIAGRAM_REGION_BEFORE_BOUNDARY_CURVES")
            shown.add(ident)
            ordered.append(ident)
        checked[scene.event_id]=dict(row)
    if set(objects)!=shown:
        raise LongboardError("DIAGRAM_INCOMPLETE_REVEAL")
    return DiagramContract(payload["kind"],scenes[0].event_id,objects,checked,
                           tuple(ordered),plan.source_storyboard_sha256)
