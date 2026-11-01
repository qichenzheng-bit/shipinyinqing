"""Frame-rate defaults and real-time duration policies for video output.

60 FPS is the default for NEW video renders and edit sessions. Explicit older
FPS settings remain supported for reproducibility of legacy projects. Timing
is expressed in seconds and converted at the chosen FPS, never hardcoded to
an old 30-FPS frame count.
"""
from __future__ import annotations

DEFAULT_VIDEO_FPS = 60
MIN_VIDEO_FPS = 8
MAX_VIDEO_FPS = 60
BOARD_WIPE_SECONDS = 0.6


def transition_frame_count(fps: int) -> int:
    """Maintain a 0.6-second board wipe at any supported output frame rate."""
    if type(fps) is not int or not MIN_VIDEO_FPS <= fps <= MAX_VIDEO_FPS:
        raise ValueError("VIDEO_FPS_OUT_OF_RANGE")
    return max(1, round(BOARD_WIPE_SECONDS * fps))
