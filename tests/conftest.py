"""Shared fixtures: ffmpeg-synthesised clips (no network).

Clip builders adapted from bradautomates/claude-video (MIT,
https://github.com/bradautomates/claude-video).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

COLORS = ["red", "green", "blue", "white", "black", "yellow", "cyan", "magenta"]


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr}")


def build_cut_clip(path: Path, n: int = 8, seg: float = 0.5, size: str = "320x240", fps: int = 10) -> None:
    """n solid-colour segments concatenated — a hard scene cut at every boundary."""
    inputs: list[str] = []
    for i in range(n):
        inputs += ["-f", "lavfi", "-t", str(seg), "-i", f"color=c={COLORS[i % len(COLORS)]}:s={size}:r={fps}"]
    streams = "".join(f"[{i}:v]" for i in range(n))
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", f"{streams}concat=n={n}:v=1:a=0[out]", "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-force_key_frames", f"expr:gte(t,n_forced*{seg})",
        str(path),
    ])


def build_static_clip(path: Path, duration: float = 3.0, size: str = "320x240", fps: int = 10) -> None:
    """One solid colour for the whole clip: no scene changes."""
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-t", str(duration), "-i", f"color=c=blue:s={size}:r={fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
    ])


@pytest.fixture(scope="session")
def cut_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clips") / "cuts.mp4"
    build_cut_clip(path)
    return path


@pytest.fixture(scope="session")
def static_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clips") / "static.mp4"
    build_static_clip(path)
    return path
