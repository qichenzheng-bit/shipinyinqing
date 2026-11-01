"""V2.6.6.2 conservative, verifiable edit impact analysis.

This is NOT an LLM's unchecked guess. It compares the actual verified JSON
package before/after each transaction, identifies changed source identities,
and only marks a unit reusable if all source, speech, layout and entry-state
inputs used by its cache key remain valid.

Changed stage clocks propagate globally; they do not automatically invalidate
unchanged stage visuals. Changes to mathematical source can invalidate later
proofs / recalls and therefore conservatively propagate to downstream stages.
"""
from __future__ import annotations

import json
from pathlib import Path

from .render_cache import digest


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def _changes(before, after, path=""):
    if before == after:
        return []
    if type(before) is dict and type(after) is dict:
        return [
            c for name in sorted(set(before) | set(after))
            for c in _changes(
                before.get(name,object()),after.get(name,object()),
                path + "/" + name.replace("~","~0").replace("/","~1"),
            )
        ]
    if type(before) is list and type(after) is list:
        return [
            c for n in range(max(len(before),len(after)))
            for c in _changes(
                before[n] if n<len(before) else object(),
                after[n] if n<len(after) else object(),
                path+"/"+str(n),
            )
        ]
    return [path or "/"]


def analyze_impact(before_package: Path, after_package: Path,
                   operations: list[dict]) -> dict:
    before_package=Path(before_package)
    after_package=Path(after_package)
    manifest=_read(before_package/"unified_flow.json")
    if not isinstance(manifest,dict):
        raise ValueError("IMPACT_NO_SOURCE_FLOW")
    ids=[s["stage_id"] for s in manifest["stages"]]
    if not ids or len(set(ids))!=len(ids):
        raise ValueError("IMPACT_STAGE_ORDER_INVALID")
    before_spoken=_read(before_package/"spoken_classroom.json")
    after_spoken=_read(after_package/"spoken_classroom.json")
    if before_spoken is None or after_spoken is None:
        raise ValueError("IMPACT_SPOKEN_SOURCE_MISSING")
    changed_files=sorted({x["file"] for x in operations})
    changed_pointers={}
    for name in changed_files:
        p0=_read(before_package/name)
        p1=_read(after_package/name)
        if p0==p1:
            # Returning zero changes after a valid plan must be impossible.
            raise ValueError("IMPACT_NO_EFFECT")
        changed_pointers[name]=_changes(p0,p1)
    math_source_changed=False
    global_invalidation=False
    affected=set()
    changed_actions=[]
    reasons=[]
    if "spoken_classroom.json" in changed_files:
        # Replacing the entire voice or moving/adding/removing event blocks
        # requires conservative whole-lesson resynchronization.
        if (before_spoken.get("voice")!=after_spoken.get("voice") or
                len(before_spoken.get("events",[]))!=
                len(after_spoken.get("events",[]))):
            global_invalidation=True
            reasons.append("VOICE_OR_EVENT_STRUCTURE_CHANGED")
        old_events=before_spoken.get("events",[])
        new_events=after_spoken.get("events",[])
        for i in range(min(len(old_events),len(new_events))):
            old,new=old_events[i],new_events[i]
            if old!=new:
                stage=new.get("stage_id",old.get("stage_id"))
                event=new.get("event_id",old.get("event_id"))
                if stage not in ids:
                    global_invalidation=True
                else:
                    affected.add(stage)
                old_spans=old.get("spans",[])
                new_spans=new.get("spans",[])
                if (len(old_spans)!=len(new_spans) or
                        old.get("event_id")!=new.get("event_id") or
                        old.get("stage_id")!=new.get("stage_id")):
                    global_invalidation=True
                    reasons.append("SPOKEN_EVENT_ACTION_STRUCTURE_CHANGED")
                for j in range(max(len(old_spans),len(new_spans))):
                    old_span=old_spans[j] if j<len(old_spans) else None
                    new_span=new_spans[j] if j<len(new_spans) else None
                    if old_span!=new_span:
                        changed_actions.append({
                            "stage_id":stage,
                            "event_id":event,
                            "object_id":(
                                new_span.get("object_id")
                                if isinstance(new_span,dict) else
                                old_span.get("object_id","")
                            ),
                            "span_index":j,
                            "math_pronunciation_or_display_changed": (
                                any(x.get("kind")=="math" for x in
                                    (old_span,new_span) if isinstance(x,dict))
                            ),
                        })
        if not global_invalidation:
            reasons.append("SOURCE_LINKED_SPEECH_CHANGED")
    for filename in changed_files:
        if filename=="spoken_classroom.json":
            continue
        if filename in ("unified_flow.json","adaptive_layout.json",
                        "math_memory.json"):
            global_invalidation=True
            if filename in ("unified_flow.json","math_memory.json"):
                math_source_changed=True
            reasons.append("GLOBAL_SOURCE_OR_LAYOUT_CHANGED:"+filename)
            continue
        owner=next((
            sid for sid,row in zip(ids,manifest["stages"])
            if filename.startswith(row["directory"].rstrip("/")+"/")
        ),None)
        if owner is None:
            # Unknown source JSON path is not assumed independent.
            global_invalidation=True
            math_source_changed=True
            reasons.append("UNCLASSIFIED_SOURCE_FILE:"+filename)
            continue
        math_source_changed=True
        start=ids.index(owner)
        affected.update(ids[start:])
        reasons.append("MATHEMATICAL_STAGE_AND_DOWNSTREAM:"+owner)
    if global_invalidation:
        affected=set(ids)
    # A narration speed change in one stage affects GLOBAL subtitle/event
    # offsets, but not the unchanged Manim scene content of later stages.
    updated=[x for x in ids if x in affected]
    unchanged=[x for x in ids if x not in affected]
    return {
        "schema_version":"1.0",
        "changed_files": changed_files,
        "changed_json_pointers": changed_pointers,
        "changed_spoken_actions": changed_actions,
        "affected_stages": updated,
        "reusable_stages_subject_to_cache_validation": unchanged,
        "global_timeline_recomputation_required":bool(changed_files),
        "mathematical_source_changed":math_source_changed,
        "whole_lesson_invalidation":global_invalidation,
        "reasons": sorted(set(reasons)),
        "source_impact_sha256":digest({
            "before":{f:_read(before_package/f) for f in changed_files},
            "after":{f:_read(after_package/f) for f in changed_files},
            "stage_order":ids,
        }),
    }
