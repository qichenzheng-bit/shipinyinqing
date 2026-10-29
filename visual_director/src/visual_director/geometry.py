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


def _segment_intersects_rect(a, b, rect, margin=.018):
    """Exact line-segment / expanded axis-aligned rectangle intersection.

    Nine sample points leave gaps inside wide MathTex labels. The clipping
    interval tests the full mathematical segment instead of sampled distances.
    """
    x, y, w, h = rect
    xmin, xmax = x - margin, x + w + margin
    ymin, ymax = y - margin, y + h + margin
    dx, dy = b[0] - a[0], b[1] - a[1]
    lower, upper = 0.0, 1.0
    for direction, distance in (
        (-dx, a[0] - xmin), (dx, xmax - a[0]),
        (-dy, a[1] - ymin), (dy, ymax - a[1]),
    ):
        if direction == 0:
            if distance < 0:
                return False
            continue
        ratio = distance / direction
        if direction < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return True


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
            if any(_segment_intersects_rect(a, b, rect) for a, b in segments):
                continue
            chosen=LabelPlacement(point_id=pt.id,text_latex=pt.label,x=x,y=y,w=ww,h=hh)
            break
        if chosen is None:
            raise GeometryError(f"LABEL_PLACEMENT_FAILED: no safe location for {pt.id}")
        placed.append(chosen)
    return DiagramPlacement(points=spec.points,lines=spec.lines,curves=spec.curves,labels=placed)