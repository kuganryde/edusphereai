"""A synthesized alert tone — no bundled audio asset required."""

from __future__ import annotations

import io
import wave

import numpy as np


def generate_beep_wav(freq: float = 950.0, duration: float = 0.35, sample_rate: int = 22050) -> bytes:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * freq * t)
    attack, release = 0.02, 0.05
    envelope = np.clip(np.minimum(t / attack, (duration - t) / release), 0.0, 1.0)
    samples = (tone * envelope * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()
