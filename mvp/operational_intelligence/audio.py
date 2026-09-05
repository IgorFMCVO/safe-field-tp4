"""Continuous PCM recording and silence-based segment closure.

The raw stream is written before segmentation is evaluated.  Silence can close
a segment, but it can never pause or gate the occurrence recording.
"""

from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import Callable
import wave
import math
import sys


@dataclass(frozen=True, slots=True)
class PCMFormat:
    sample_rate: int = 16_000
    channels: int = 1
    sample_width: int = 2

    @property
    def frame_width(self) -> int:
        return self.channels * self.sample_width


@dataclass(frozen=True, slots=True)
class SegmenterConfig:
    pre_roll_ms: int = 400
    post_roll_ms: int = 400
    silence_close_ms: int = 1_500
    speech_rms_threshold: int = 500

    def __post_init__(self) -> None:
        if min(self.pre_roll_ms, self.post_roll_ms, self.silence_close_ms) < 0:
            raise ValueError("Segment timing cannot be negative")
        if self.silence_close_ms == 0:
            raise ValueError("silence_close_ms must be positive")


@dataclass(slots=True)
class AudioChunk:
    data: bytes
    start_frame: int
    end_frame: int
    rms: int
    voiced: bool


@dataclass(slots=True)
class ClosedSegment:
    data: bytes
    start_frame: int
    end_frame: int
    peak_rms: int


class SilenceSegmenter:
    def __init__(self, pcm: PCMFormat, config: SegmenterConfig):
        self.pcm = pcm
        self.config = config
        self.total_frames = 0
        self._pre_roll: deque[AudioChunk] = deque()
        self._pre_roll_frames = 0
        self._active: list[AudioChunk] | None = None
        self._silence_frames = 0

    def _frames(self, milliseconds: int) -> int:
        return round(self.pcm.sample_rate * milliseconds / 1000)

    def _remember(self, chunk: AudioChunk) -> None:
        self._pre_roll.append(chunk)
        self._pre_roll_frames += chunk.end_frame - chunk.start_frame
        limit = self._frames(self.config.pre_roll_ms)
        while self._pre_roll and self._pre_roll_frames > limit:
            removed = self._pre_roll.popleft()
            self._pre_roll_frames -= removed.end_frame - removed.start_frame

    def ingest(self, data: bytes) -> list[ClosedSegment]:
        if not data:
            return []
        if len(data) % self.pcm.frame_width:
            raise ValueError("PCM chunk is not aligned to complete frames")
        frames = len(data) // self.pcm.frame_width
        start = self.total_frames
        self.total_frames += frames
        if self.pcm.sample_width != 2:
            raise ValueError("MVP segment energy currently requires signed PCM16")
        samples = array("h")
        samples.frombytes(data)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))
        chunk = AudioChunk(data, start, self.total_frames, rms, rms >= self.config.speech_rms_threshold)
        closed: list[ClosedSegment] = []

        if self._active is None and chunk.voiced:
            self._active = list(self._pre_roll)
            self._active.append(chunk)
            self._silence_frames = 0
        elif self._active is not None:
            self._active.append(chunk)
            if chunk.voiced:
                self._silence_frames = 0
            else:
                self._silence_frames += frames
                close_after = self._frames(
                    self.config.silence_close_ms + self.config.post_roll_ms
                )
                if self._silence_frames >= close_after:
                    closed.append(self._close())

        self._remember(chunk)
        return closed

    def _close(self) -> ClosedSegment:
        assert self._active
        active = self._active
        self._active = None
        self._silence_frames = 0
        return ClosedSegment(
            data=b"".join(chunk.data for chunk in active),
            start_frame=active[0].start_frame,
            end_frame=active[-1].end_frame,
            peak_rms=max(chunk.rms for chunk in active),
        )

    def flush(self) -> list[ClosedSegment]:
        return [self._close()] if self._active else []


class ContinuousAudioRecorder:
    """Writes a lossless stream and emits durable WAV segments."""

    def __init__(
        self,
        session_root: Path,
        pcm: PCMFormat,
        segmenter_config: SegmenterConfig,
        on_segment: Callable[[Path, dict], None],
    ):
        self.session_root = session_root
        self.pcm = pcm
        self.segmenter = SilenceSegmenter(pcm, segmenter_config)
        self.on_segment = on_segment
        self._lock = threading.Lock()
        self._closed = False
        self._segment_number = 0
        self.raw_path = session_root / "audio" / "raw.wav"
        self.processed_path = session_root / "audio" / "processed.wav"
        self._raw = self._open_wav(self.raw_path)
        # MVP v1 keeps an unmodified processing input copy; later processing must
        # never overwrite raw.wav.
        self._processed = self._open_wav(self.processed_path)

    def _open_wav(self, path: Path) -> wave.Wave_write:
        stream = wave.open(str(path), "wb")
        stream.setnchannels(self.pcm.channels)
        stream.setsampwidth(self.pcm.sample_width)
        stream.setframerate(self.pcm.sample_rate)
        return stream

    def ingest(self, data: bytes) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Audio recorder is closed")
            # This happens unconditionally and before any silence decision.
            self._raw.writeframesraw(data)
            self._processed.writeframesraw(data)
            closed = self.segmenter.ingest(data)
        for segment in closed:
            self._persist(segment)

    def _persist(self, segment: ClosedSegment) -> None:
        self._segment_number += 1
        segment_id = f"segment_{self._segment_number:04d}"
        path = self.session_root / "segments" / f"{segment_id}.wav"
        with self._open_wav(path) as stream:
            stream.writeframes(segment.data)
        metadata = {
            "segment_id": segment_id,
            "audio_path": str(path),
            "start": segment.start_frame / self.pcm.sample_rate,
            "end": segment.end_frame / self.pcm.sample_rate,
            "duration": (segment.end_frame - segment.start_frame) / self.pcm.sample_rate,
            "peak_rms": segment.peak_rms,
            "status": "QUEUED",
        }
        path.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # The production callback is a non-blocking queue submit.
        self.on_segment(path, metadata)

    def close(self) -> dict:
        with self._lock:
            if self._closed:
                return {"frames": self.segmenter.total_frames, "segments": self._segment_number}
            pending = self.segmenter.flush()
            self._raw.close()
            self._processed.close()
            self._closed = True
        for segment in pending:
            self._persist(segment)
        return {"frames": self.segmenter.total_frames, "segments": self._segment_number}
