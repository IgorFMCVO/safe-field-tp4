"""Durable, background processing pipeline for closed audio segments."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import queue
import threading
import time
from typing import Any

from .fact_graph import FactGraph
from .models import (
    EvidenceStatus,
    Fact,
    Hypothesis,
    HypothesisStatus,
    ProcessingStatus,
    TranscriptSegment,
    utc_now,
    validate_artifact_id,
)
from .providers import (
    ASRProvider,
    DiarizationProvider,
    KnowledgeProvider,
    ReasoningProvider,
    SpeakerEmbeddingProvider,
)
from .speaker_registry import SpeakerRegistry
from .storage import Timeline, atomic_json


@dataclass(slots=True)
class PipelineProviders:
    asr: ASRProvider
    diarization: DiarizationProvider
    embedding: SpeakerEmbeddingProvider
    reasoning: ReasoningProvider
    knowledge: KnowledgeProvider


def _fact_from_dict(data: dict) -> Fact:
    normalized = dict(data)
    normalized["status"] = EvidenceStatus(normalized["status"])
    return Fact(**normalized)


def _hypothesis_from_dict(data: dict) -> Hypothesis:
    normalized = dict(data)
    normalized["status"] = HypothesisStatus(normalized["status"])
    normalized["evidence_status"] = EvidenceStatus(normalized["evidence_status"])
    return Hypothesis(**normalized)


class AsyncSegmentPipeline:
    """Runs inference in a worker without making capture await providers.

    `submit_segment` uses an unbounded SimpleQueue and returns immediately.  The
    segment WAV and JSON sidecar already exist on disk, so a provider outage can
    be retried later without losing the source.
    """

    _STOP = object()

    def __init__(
        self,
        session_root: Path,
        providers: PipelineProviders,
        speaker_registry: SpeakerRegistry,
        timeline: Timeline,
    ):
        self.session_root = session_root
        self.providers = providers
        self.speaker_registry = speaker_registry
        self.timeline = timeline
        self.fact_graph = FactGraph(session_root / "facts" / "fact_graph.json")
        self._queue: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._condition = threading.Condition()
        self._pending = 0
        self._completed = 0
        self._failed = 0
        self._thread = threading.Thread(target=self._worker, daemon=True, name="safe-field-pipeline")
        self._thread.start()

    @property
    def pending(self) -> int:
        with self._condition:
            return self._pending

    @property
    def stats(self) -> dict[str, int]:
        with self._condition:
            return {
                "pending": self._pending,
                "completed": self._completed,
                "failed": self._failed,
            }

    def submit_segment(self, audio_path: Path, metadata: dict) -> None:
        job = {"kind": "segment", "audio_path": str(audio_path), "metadata": dict(metadata)}
        job_path = self.session_root / "jobs" / f"{metadata['segment_id']}.json"
        atomic_json(job_path, {**job, "status": ProcessingStatus.QUEUED.value})
        with self._condition:
            self._pending += 1
        self._queue.put(job)
        self.timeline.append("SEGMENT_QUEUED", segment_id=metadata["segment_id"])

    def submit_confirmation(self, hypothesis_id: str, decision: str) -> None:
        validate_artifact_id(hypothesis_id, "hypothesis_id")
        normalized = decision.upper()
        if normalized not in {"CONFIRM", "REJECT", "MORE_DATA"}:
            raise ValueError("Unsupported officer decision")
        job = {"kind": "confirmation", "hypothesis_id": hypothesis_id, "decision": normalized}
        job_path = self.session_root / "jobs" / f"confirmation_{hypothesis_id}_{int(time.time_ns())}.json"
        atomic_json(job_path, {**job, "status": ProcessingStatus.QUEUED.value})
        with self._condition:
            self._pending += 1
        self._queue.put(job)
        self.timeline.append(
            "WATCH_CONFIRMATION_QUEUED", hypothesis_id=hypothesis_id, decision=normalized
        )

    def drain(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._pending:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self, timeout: float = 5.0) -> None:
        self._queue.put(self._STOP)
        self._thread.join(timeout)

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            if job is self._STOP:
                return
            failed = False
            try:
                if job["kind"] == "segment":
                    asyncio.run(self._process_segment(job))
                else:
                    asyncio.run(self._process_confirmation(job))
            except Exception as exc:  # source is preserved and explicitly retryable
                failed = True
                self._record_failure(job, exc)
            finally:
                with self._condition:
                    self._pending -= 1
                    if failed:
                        self._failed += 1
                    else:
                        self._completed += 1
                    self._condition.notify_all()

    async def _process_segment(self, job: dict) -> None:
        audio_path = Path(job["audio_path"])
        metadata = job["metadata"]
        segment_id = metadata["segment_id"]
        job_path = self.session_root / "jobs" / f"{segment_id}.json"
        atomic_json(job_path, {**job, "status": ProcessingStatus.PROCESSING.value})
        self.timeline.append("SEGMENT_PROCESSING", segment_id=segment_id)

        asr = await self.providers.asr.transcribe(audio_path)
        # Persist the irreplaceable ASR output before any downstream provider is
        # called.  Diarization or embedding may be temporarily unavailable; in
        # that case raw_transcript must still survive beside the pending job.
        transcript = TranscriptSegment(
            segment_id=segment_id,
            speaker_ids=[],
            start=metadata["start"],
            end=metadata["end"],
            raw_transcript=asr.text,
            asr_confidence=asr.confidence,
            audio_path=str(audio_path),
        )
        transcript_path = self.session_root / "transcripts" / f"{segment_id}.json"
        atomic_json(transcript_path, transcript.to_dict())
        self.timeline.append("TRANSCRIPT_READY", segment_id=segment_id)
        turns = list(await self.providers.diarization.diarize(audio_path, asr))
        if not turns:
            raise ValueError("Diarization returned no speaker turns")

        speaker_ids: list[str] = []
        for turn in turns:
            embedding = await self.providers.embedding.embed(audio_path, turn.start, turn.end)
            record, similarity = self.speaker_registry.register(
                embedding, segment_id, provider_confidence=turn.confidence
            )
            if record.speaker_id not in speaker_ids:
                speaker_ids.append(record.speaker_id)
            self.timeline.append(
                "SPEAKER_ASSIGNED",
                segment_id=segment_id,
                speaker_id=record.speaker_id,
                match_status=record.match_status.value,
                similarity=similarity,
            )

        transcript.speaker_ids = speaker_ids
        atomic_json(transcript_path, transcript.to_dict())
        reasoning = await self.providers.reasoning.analyze(transcript)

        for speaker_id, role in reasoning.provisional_roles.items():
            if speaker_id in {record.speaker_id for record in self.speaker_registry.records}:
                self.speaker_registry.set_provisional_role(speaker_id, role)

        for fact in reasoning.facts:
            if segment_id not in fact.source_segments:
                raise ValueError(f"Fact {fact.fact_id} is not traceable to the current segment")
            if not set(fact.source_speakers).issubset(speaker_ids):
                raise ValueError(f"Fact {fact.fact_id} references a speaker absent from its transcript")
            self.fact_graph.add_fact(fact)
            atomic_json(self.session_root / "facts" / f"{fact.fact_id}.json", fact.to_dict())
        for hypothesis in reasoning.hypotheses:
            if segment_id not in hypothesis.source_segments:
                raise ValueError(
                    f"Hypothesis {hypothesis.hypothesis_id} is not traceable to the current segment"
                )
            missing_facts = [
                fact_id
                for fact_id in hypothesis.supporting_facts + hypothesis.contradictory_facts
                if not self.fact_graph.has_fact(fact_id)
            ]
            if missing_facts:
                raise ValueError(
                    f"Hypothesis {hypothesis.hypothesis_id} references missing facts: {missing_facts}"
                )
            atomic_json(
                self.session_root / "hypotheses" / f"{hypothesis.hypothesis_id}.json",
                hypothesis.to_dict(),
            )
        atomic_json(
            self.session_root / "facts" / f"analysis_{segment_id}.json",
            {
                "segment_id": segment_id,
                "contradictions": reasoning.contradictions,
                "information_gaps": reasoning.information_gaps,
            },
        )
        sidecar = audio_path.with_suffix(".json")
        atomic_json(sidecar, {**metadata, "status": ProcessingStatus.COMPLETE.value})
        atomic_json(job_path, {**job, "status": ProcessingStatus.COMPLETE.value})
        self.timeline.append(
            "INTELLIGENCE_READY",
            segment_id=segment_id,
            facts=len(reasoning.facts),
            hypotheses=len(reasoning.hypotheses),
        )

    async def _process_confirmation(self, job: dict) -> None:
        hypothesis_id = job["hypothesis_id"]
        path = self.session_root / "hypotheses" / f"{hypothesis_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown hypothesis: {hypothesis_id}")
        hypothesis = _hypothesis_from_dict(json.loads(path.read_text(encoding="utf-8")))
        decision = job["decision"]
        if decision == "MORE_DATA":
            self.timeline.append("MORE_DATA_REQUESTED", hypothesis_id=hypothesis_id)
            return
        hypothesis.status = (
            HypothesisStatus.OFFICER_CONFIRMED
            if decision == "CONFIRM"
            else HypothesisStatus.OFFICER_REJECTED
        )
        hypothesis.evidence_status = EvidenceStatus.OFFICER_CONFIRMED
        hypothesis.officer_decision_at = utc_now()
        atomic_json(path, hypothesis.to_dict())
        self.timeline.append(
            "HYPOTHESIS_OFFICER_DECISION",
            hypothesis_id=hypothesis_id,
            decision=decision,
        )
        if decision != "CONFIRM":
            return

        facts = []
        missing_facts = []
        for fact_id in hypothesis.supporting_facts:
            fact_path = self.session_root / "facts" / f"{fact_id}.json"
            if fact_path.exists():
                facts.append(_fact_from_dict(json.loads(fact_path.read_text(encoding="utf-8"))))
            else:
                missing_facts.append(fact_id)
        if missing_facts:
            raise ValueError(f"Confirmed hypothesis references missing facts: {missing_facts}")
        guidance = await self.providers.knowledge.retrieve_guidance(hypothesis, facts)
        guidance.ensure_supported()
        atomic_json(
            self.session_root / "guidance" / f"{hypothesis_id}.json",
            {
                "hypothesis_id": guidance.hypothesis_id,
                "status": guidance.status,
                "items": [
                    {
                        "text": item.text,
                        "sources": [
                            {
                                "source_document": source.source_document,
                                "source_version": source.source_version,
                                "section": source.section,
                                "page": source.page,
                                "item": source.item,
                                "chunk_id": source.chunk_id,
                                "relevance": source.relevance,
                            }
                            for source in item.sources
                        ],
                    }
                    for item in guidance.items
                ],
            },
        )
        self.timeline.append("GUIDANCE_READY", hypothesis_id=hypothesis_id)

    def _record_failure(self, job: dict, exc: Exception) -> None:
        identifier = job.get("metadata", {}).get("segment_id") or job.get("hypothesis_id", "unknown")
        failure = {
            **job,
            "status": ProcessingStatus.PROCESSING_PENDING.value,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "failed_at": utc_now(),
        }
        atomic_json(self.session_root / "jobs" / f"pending_{identifier}.json", failure)
        if job["kind"] == "segment":
            sidecar = Path(job["audio_path"]).with_suffix(".json")
            atomic_json(sidecar, {**job["metadata"], "status": ProcessingStatus.PROCESSING_PENDING.value})
        elif str(exc) == "GUIDANCE_NOT_AVAILABLE":
            atomic_json(
                self.session_root / "guidance" / f"{identifier}.json",
                {"hypothesis_id": identifier, "status": "GUIDANCE_NOT_AVAILABLE", "items": []},
            )
        self.timeline.append(
            "PROCESSING_PENDING", job_kind=job["kind"], identifier=identifier, reason=str(exc)
        )
