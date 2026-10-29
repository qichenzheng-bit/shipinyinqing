"""Conservative deterministic diagram label placement in diagram-local space.

This is not a renderer's pixel collision test: real font outlines require a
separate, downstream measurement pass. Mathematical intersections are allowed.
"""
from __future__ import annotations
import math
from .models import DiagramSpec, DiagramPlacement, LabelPlacement


class GeometryError(ValueError):
    pass


def _distance_to_segment(x: float, y: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    d = vx*vx + vy*vy
    t = max(0., min(1., ((x-a[0])*vx+(y-a[1])*vy)/d)) if d else 0.
    return math.hypot(x-a[0]-t*vx, y-a[1]-t*vy)


def _rectangle_segments(rect, samples):
    x, y, w, h = rect
    # 9 interior sample points approximate proximity to lines without saying
    # anything about mathematical point/line intersections themselves.
    return [(x+u*w, y+v*h) for u in (0, .5, 1) for v in (0, .5, 1)]


def place_diagram(spec: DiagramSpec) -> DiagramPlacement:
    points = {p.id: p for p in spec.points}
    if len(points) != len(spec.points):
        raise GeometryError("DIAGRAM_REFERENCE: duplicate point IDs")
    line_ids = [l.id for l in spec.lines] + [c.id for c in spec.curves]
    if len(line_ids) != len(set(line_ids)) or set(line_ids) & set(points):
        raise GeometryError("DIAGRAM_REFERENCE: duplicate diagram IDs")
    segments = []
    for line in spec.lines:
        if line.start not in points or line.end not in points:
            raise GeometryError("DIAGRAM_REFERENCE: line refers to unknown point")
        a,b=points[line.start],points[line.end]
        segments.append(((a.x,a.y),(b.x,b.y)))
    for curve in spec.curves:
        if len(curve.points)<2 or any(not(0<=x<=1 and 0<=y<=1) for x,y in curve.points):
            raise GeometryError("DIAGRAM_REFERENCE: invalid curve samples")
        segments.extend(zip(curve.points, curve.points[1:]))

    placed=[]
    for pt in spec.points:
        if not pt.label.strip():
            continue
        # Coarse LaTeX text bounding box. Actual MathTex size must be checked at
        # render time. Avoid using spoken phonetic strings as visual labels.
        w=min(.20,max(.045,len(pt.label)*.014+.028))
        h=.055
        offsets=[(.045,-.085),(-w-.045,-.085),(.045,.045),(-w-.045,.045),
                 (-w/2,-.13),(-w/2,.075),(.10,-.025),(-w-.10,-.025)]
        chosen=None
        for dx,dy in offsets:
            rect=(pt.x+dx,pt.y+dy,w,h)
            x,y,ww,hh=rect
            if x<.015 or y<.015 or x+ww>.985 or y+hh>.985:
                continue
            if any(x-.025<=p.x<=x+ww+.025 and y-.025<=p.y<=y+hh+.025 for p in spec.points):
                continue
            if any(not(x+ww+.015<=p.x or p.x+p.w+.015<=x or y+hh+.015<=p.y or p.y+p.h+.015<=y) for p in placed):
                continue
            if any(_distance_to_segment(cx,cy,a,b)<.018 for a,b in segments for cx,cy in _rectangle_segments(rect, None)):
                continue
            chosen=LabelPlacement(point_id=pt.id,text_latex=pt.label,x=x,y=y,w=ww,h=hh)
            break
        if chosen is None:
            raise GeometryError(f"LABEL_PLACEMENT_FAILED: no safe location for {pt.id}")
        placed.append(chosen)
    return DiagramPlacement(points=spec.points,lines=spec.lines,curves=spec.curves,labels=placed)