"""Authentic Edge neural TTS clips with measured PCM durations.

No synthetic sine waves or fabricated durations ever qualify as spoken
output. The test suite can verify the pure sample-placement functions without
claiming real voice. Each caption is deterministically derived from exactly
the sound clip's approved semantic source part.
"""
from __future__ import annotations

import asyncio
import math
import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from .longboard_plan import LongboardError
from .spoken_classroom import SpokenContract, DEFAULT_SPEECH_RATE

SAMPLE_RATE = 24000


@dataclass(frozen=True)
class VoiceChunk:
    kind: str
    display: str
    voice_text: str
    raw_pcm: bytes
    sample_count: int
    frames: int


@dataclass(frozen=True)
class VoicedSpan:
    kind: str
    object_id: str
    chunks: tuple[VoiceChunk, ...]
    frames: int
    math_start_frame: int | None
    diagram_beats: tuple[dict, ...] = ()

    def duration(self, fps: int) -> float:
        return self.frames / fps


def split_natural_phrases(text: str, *, limit: int = 23) -> list[str]:
    """Short semantic clauses rather than complete sentences prematurely shown."""
    if not text or not text.strip():
        raise LongboardError("VOICE_EMPTY_SPEECH")
    # Preserve full punctuation: subtitles and audio have the same clauses.
    clauses = re.findall(r"[^，。！？；]+[，。！？；]?", text)
    result = []
    for clause in clauses:
        if not clause.strip():
            continue
        if len(clause) <= limit:
            result.append(clause)
        else:
            # Never silently omit pedagogical words. Reviewers can write
            # smaller punctuation-delimited clauses for better cadence.
            # Never cut a mathematical expression or Chinese word simply
            # because a character quota was reached. Use an explicit semantic
            # connector; otherwise ask the author to punctuate the clause.
            remaining = clause
            while len(remaining) > limit:
                points = [
                    m.start() for m in re.finditer(
                        r"(?=因此|所以|于是|接下来|然后|首先|同时|最后|注意|另外|我们|这时)",
                        remaining,
                    )
                    if 4 <= m.start() <= limit
                ]
                if not points:
                    raise LongboardError("VOICE_UNSAFE_LONG_CLAUSE: add a natural pause")
                cut = max(points)
                result.append(remaining[:cut])
                remaining = remaining[cut:]
            if remaining:
                result.append(remaining)
    if "".join(result) != text:
        raise LongboardError("VOICE_PHRASE_SOURCE_MUTATED")
    return result


def _decode_mp3_to_pcm(mp3: Path, wav: Path) -> bytes:
    p = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(mp3), "-ar", str(SAMPLE_RATE), "-ac", "1",
        "-c:a", "pcm_s16le", str(wav),
    ], capture_output=True, text=True)
    if p.returncode or not wav.is_file():
        raise LongboardError("VOICE_DECODE_FAILED: "+p.stderr[-300:])
    with wave.open(str(wav),"rb") as stream:
        if (stream.getnchannels()!=1 or
                stream.getframerate()!=SAMPLE_RATE or
                stream.getsampwidth()!=2):
            raise LongboardError("VOICE_UNVERIFIED_PCM_FORMAT")
        data=stream.readframes(stream.getnframes())
    if len(data) < SAMPLE_RATE:  # at least half a second
        raise LongboardError("VOICE_AUDIO_MISSING")
    from array import array
    decoded=array("h")
    decoded.frombytes(data)
    if not any(abs(decoded[i]) > 35 for i in range(0,len(decoded),75)):
        raise LongboardError("VOICE_WAVEFORM_IS_SILENT")
    return data


async def _edge_clip(index: int, text: str, voice: str,
                     root: Path, semaphore, cache=None,
                     rate: str=DEFAULT_SPEECH_RATE) -> bytes:
    try:
        import edge_tts
    except ImportError as exc:
        raise LongboardError(
            "VOICE_TTS_PROVIDER_MISSING: pip install edge-tts"
        ) from exc
    # Key includes voice, actual speed, source text, sample-rate and code/
    # provider versions (the cache itself supplies the runtime signature).
    cache_key=(cache.key("speech_pcm",{
        "text":text,"voice":voice,"rate":rate,
        "sample_rate":SAMPLE_RATE,"codec":"pcm_s16le_mono",
    }) if cache is not None else None)
    async with semaphore:
        if cache is not None:
            previous=cache.get_pcm(cache_key)
            if previous is not None:
                return previous
        mp3=root/f"spoken_{index:04d}.mp3"
        wav=root/f"spoken_{index:04d}.wav"
        last=None
        for attempt in range(2):
            try:
                await asyncio.wait_for(
                    edge_tts.Communicate(
                        text, voice=voice, rate=rate,
                    ).save(str(mp3)),
                    timeout=35,
                )
                if not mp3.is_file() or mp3.stat().st_size < 200:
                    raise LongboardError("VOICE_PROVIDER_RETURNED_NO_AUDIO")
                pcm=_decode_mp3_to_pcm(mp3,wav)
                if cache is not None:
                    cache.write("speech_pcm",cache_key,{"payload.bin":pcm})
                return pcm
            except Exception as exc:
                last=exc
                if attempt == 0:
                    await asyncio.sleep(.7)
        raise LongboardError(
            f"VOICE_AUTHENTIC_TTS_FAILED: {type(last).__name__}: {str(last)[:120]}"
        ) from last


async def synthesize_voiced_spans(contract: SpokenContract, root: Path,
                                  *, fps: int, cache=None) -> dict:
    if type(fps) is not int or fps < 8 or fps > 60:
        raise LongboardError("VOICE_FPS_INVALID")
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    requests=[]
    skeleton=[]
    index=0
    for event in contract.events:
        spans=[]
        for span in event.spans:
            keys=[]
            for part in span.parts:
                if part["kind"]=="text":
                    for phrase in split_natural_phrases(part["value"]):
                        requests.append((index,phrase,contract.voice,contract.speech_rate))
                        keys.append((index,"text",phrase,phrase))
                        index+=1
                else:
                    requests.append((index,part["reading"],contract.voice,contract.speech_rate))
                    keys.append((index,"math",part.get("spoken_math_latex",part["latex"]),part["reading"]))
                    index+=1
            spans.append((span,keys))
        skeleton.append((event,spans))
    # Identical clauses share one provider invocation, even within the same
    # run; different text, voice or actual speech speed must NEVER be reused.
    semaphore=asyncio.Semaphore(4)
    unique={}
    for i,txt,voice,rate in requests:
        unique.setdefault((txt,voice,rate),(i,txt,voice,rate))
    found=await asyncio.gather(*(
        _edge_clip(i,txt,voice,root,semaphore,cache=cache,rate=rate)
        for i,txt,voice,rate in unique.values()
    ))
    by_phrase=dict(zip(unique,found))
    raw={i:by_phrase[(txt,voice,rate)] for i,txt,voice,rate in requests}
    if cache is not None:
        cache.counts["speech_same_run_deduplicated"]+=(
            len(requests)-len(unique)
        )
    result={}
    for event,spans in skeleton:
        collected=[]
        for span,keys in spans:
            built=[]
            start_math=None
            for key,kind,display,tts in keys:
                data=raw[key]
                count=len(data)//2
                if count<=0:
                    raise LongboardError("VOICE_EMPTY_DECODED_AUDIO")
                # Preserve sample-exact speech. Reserve two silent frames to
                # absorb codec rounding; do not stretch natural pronunciation.
                frames=max(4,math.ceil(count*fps/SAMPLE_RATE)+2)
                if kind=="math" and start_math is None:
                    start_math=sum(c.frames for c in built)
                built.append(VoiceChunk(
                    kind,display,tts,data,count,frames
                ))
            total=sum(c.frames for c in built)
            if total / fps > 60:
                raise LongboardError("VOICE_ACTION_TOO_LONG_SPLIT_THE_TEACHING_UNIT")
            if span.kind=="math" and start_math is None:
                raise LongboardError("VOICE_MATH_NOT_SPOKEN")
            beats = []
            if span.diagram_phrase_cues:
                phrases = {}
                cursor = 0
                for chunk in built:
                    if chunk.kind == "text":
                        phrases.setdefault(chunk.display, []).append(
                            (cursor, cursor + chunk.frames)
                        )
                    cursor += chunk.frames
                grouped = {}
                for cue in span.diagram_phrase_cues:
                    grouped.setdefault(cue["phrase"], []).append(cue["object_id"])
                for phrase, ids in grouped.items():
                    if len(phrases.get(phrase, [])) != 1:
                        raise LongboardError("VOICE_DIAGRAM_PHRASE_NOT_UNIQUE")
                    start, end = phrases[phrase][0]
                    for i, ident in enumerate(ids):
                        a = start + (end - start) * i // len(ids)
                        b = start + (end - start) * (i + 1) // len(ids)
                        if b - a < 3:
                            raise LongboardError("VOICE_DIAGRAM_BEAT_TOO_SHORT")
                        beats.append({"object_id": ident, "start_frame": a, "end_frame": b})
                beats.sort(key=lambda b: b["start_frame"])
            collected.append(VoicedSpan(
                span.kind,span.object_id,tuple(built),total,start_math,tuple(beats)
            ))
        result.setdefault(event.stage_id,{})[event.event_id]=tuple(collected)
    return result


def build_render_schedules(voiced: dict, *, fps: int) -> dict:
    schedules={}
    for stage,events in voiced.items():
        schedules[stage]={}
        for eid,spans in events.items():
            scripts=[]
            for span in spans:
                data={
                    "kind":span.kind,"object_id":span.object_id,
                    "duration":span.duration(fps),
                }
                if span.kind=="math":
                    data["math_start_delay"]=span.math_start_frame/fps
                if span.kind=="diagram" and span.diagram_beats:
                    data["diagram_beats"] = [{
                        "object_id": b["object_id"],
                        "start_offset": b["start_frame"] / fps,
                        "end_offset": b["end_frame"] / fps,
                    } for b in span.diagram_beats]
                scripts.append(data)
            schedules[stage][eid]=scripts
    return schedules


def assemble_source_pcm(voiced: dict, video_manifest: dict,
                        output_wav: Path, *, fps: int) -> list[dict]:
    """Sample-accurate placement uses measured true Manim action starts."""
    stages={
        x["stage_id"]: x["start_frame"]
        for x in video_manifest["stage_render_reports"]
    }
    total_frames=video_manifest["actual_video_frames"]
    total_samples=math.ceil((total_frames+1)*SAMPLE_RATE/fps)
    buffer=bytearray(total_samples*2)
    used=[]
    subtitle=[]
    seen=set()
    for event in video_manifest["event_timing"]:
        sid,eid=event["stage_id"],event["event_id"]
        spans=voiced[sid][eid]
        reported=event.get("action_timing",[])
        if len(spans)!=len(reported):
            raise LongboardError("VOICE_ACTION_TIMELINE_INCOMPLETE")
        for span,actual in zip(spans,reported):
            key=(sid,eid,span.kind,span.object_id)
            if key in seen:
                raise LongboardError("VOICE_DUPLICATE_VIDEO_ACTION")
            seen.add(key)
            if (actual["kind"],actual["object_id"])!=(
                    span.kind,span.object_id):
                raise LongboardError("VOICE_TIMELINE_WRONG_ACTION")
            frame_begin=round(actual["start_preview_second"]*fps)+stages[sid]
            frame_end=round(actual["end_preview_second"]*fps)+stages[sid]
            if abs(frame_end-frame_begin-span.frames)>2:
                raise LongboardError("VOICE_ACTUAL_VISUAL_DESYNC")
            point=round(frame_begin*SAMPLE_RATE/fps)
            for clip in span.chunks:
                begin=point
                end=begin+len(clip.raw_pcm)//2
                if end>total_samples:
                    raise LongboardError("VOICE_OUTSIDE_FINAL_VIDEO")
                used.append((begin,end))
                offset=2*begin
                buffer[offset:offset+len(clip.raw_pcm)] = clip.raw_pcm
                end_frame=math.ceil(end*fps/SAMPLE_RATE)
                start_frame=round(begin*fps/SAMPLE_RATE)
                subtitle.append({
                    "stage_id":sid,"event_id":eid,
                    "object_id":span.object_id,
                    "kind":clip.kind,
                    "display":clip.display,
                    "actual_voice_text":clip.voice_text,
                    "start_frame":start_frame,
                    "end_frame":end_frame,
                })
                point+=round(clip.frames*SAMPLE_RATE/fps)
    used.sort()
    if any(x[1]>y[0] for x,y in zip(used,used[1:])):
        raise LongboardError("VOICE_OVERLAPPING_ACTION_AUDIO")
    output_wav=Path(output_wav)
    output_wav.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(output_wav),"wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(buffer)
    return subtitle
