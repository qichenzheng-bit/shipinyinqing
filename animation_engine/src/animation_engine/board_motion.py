"""Conservative collision preflight for classroom board transitions.

A mathematical object retains the identity and exact LaTeX of its source.
This module checks layout boxes over a sampled transition; if interpolated
survivor footprints would collide, the caller must use an invisible
repositioning transition instead of visibly moving through other maths.
"""
from __future__ import annotations


def overlaps(a: dict, b: dict, margin: float = 2.0) -> bool:
    return (
        a["x"] < b["x"] + b["w"] + margin
        and a["x"] + a["w"] + margin > b["x"]
        and a["y"] < b["y"] + b["h"] + margin
        and a["y"] + a["h"] + margin > b["y"]
    )


def interpolated_collisions(
    previous: dict[str, dict],
    targets: dict[str, dict],
    samples: int = 32,
) -> list[dict]:
    """Return exact object-ID pairs whose footprints overlap mid-motion.

    Only two objects visible throughout the motion are compared. New source
    Write objects are rendered after the survivor motion completes.
    """
    surviving = sorted(set(previous).intersection(targets))
    collisions = []
    for i, first in enumerate(surviving):
        for second in surviving[i+1:]:
            for frame in range(samples+1):
                t = frame / samples
                def box(object_id: str) -> dict:
                    start, end = previous[object_id], targets[object_id]
                    return {
                        field: start[field]*(1-t)+end[field]*t
                        for field in ("x", "y", "w", "h")
                    }
                if overlaps(box(first), box(second)):
                    collisions.append({
                        "first": first, "second": second,
                        "sample": frame, "samples": samples,
                    })
                    break
    return collisions


def math_placement_collisions(placements: list[dict]) -> list[tuple[str, str]]:
    collisions=[]
    for i,p in enumerate(placements):
        for other in placements[i+1:]:
            if overlaps(p,other,margin=0):
                collisions.append((p["object_id"],other["object_id"]))
    return collisions
