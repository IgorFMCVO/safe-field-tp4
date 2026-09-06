"""Traceable preliminary occurrence history generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .storage import atomic_json


def _load_json_files(paths: Iterable[Path]) -> list[dict]:
    result = []
    for path in sorted(paths):
        result.append(json.loads(path.read_text(encoding="utf-8")))
    return result


def build_preliminary_history(session_root: Path) -> tuple[Path, Path]:
    occurrence = json.loads((session_root / "occurrence.json").read_text(encoding="utf-8"))
    timeline = [
        json.loads(line)
        for line in (session_root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    speakers_doc = json.loads((session_root / "speakers" / "registry.json").read_text(encoding="utf-8"))
    transcripts = _load_json_files((session_root / "transcripts").glob("segment_*.json"))
    facts = _load_json_files(
        path
        for path in (session_root / "facts").glob("*.json")
        if not path.name.startswith("analysis_") and path.name != "fact_graph.json"
    )
    analyses = _load_json_files((session_root / "facts").glob("analysis_*.json"))
    hypotheses = _load_json_files((session_root / "hypotheses").glob("*.json"))
    guidance = _load_json_files((session_root / "guidance").glob("*.json"))
    pending = _load_json_files((session_root / "jobs").glob("pending_*.json"))
    fact_graph_path = session_root / "facts" / "fact_graph.json"
    fact_graph = json.loads(fact_graph_path.read_text(encoding="utf-8"))
    watch_path = session_root / 'watch_events.jsonl'
    watch_events = [json.loads(line) for line in watch_path.read_text(encoding='utf-8').splitlines() if line.strip()] if watch_path.exists() else []

    data = {
        "document_type": "HISTORICO_PRELIMINAR",
        "disclaimer": "Conteúdo preliminar, rastreável às fontes capturadas e sujeito à revisão policial.",
        "occurrence": occurrence,
        "timeline": timeline,
        "speakers": speakers_doc.get("speakers", []),
        "transcripts": transcripts,
        "facts": facts,
        "fact_graph": fact_graph,
        "contradictions": [item for analysis in analyses for item in analysis["contradictions"]],
        "information_gaps": [item for analysis in analyses for item in analysis["information_gaps"]],
        "hypotheses": hypotheses,
        "officer_decisions": [
            item for item in timeline if item["event"] == "HYPOTHESIS_OFFICER_DECISION"
        ],
        "guidance": guidance,
        "watch_events": watch_events,
        "guidance_actions": [event for event in watch_events if event.get('action') == 'ACTION_STATUS'],
        "pending_processing": pending,
        # Narrative uses only statements already stored as traceable facts.
        "preliminary_narrative": " ".join(fact["statement"] for fact in facts),
    }
    json_path = session_root / "reports" / "HISTORICO_PRELIMINAR.json"
    atomic_json(json_path, data)

    lines = [
        "# HISTÓRICO PRELIMINAR",
        "",
        "> Conteúdo preliminar, rastreável às fontes capturadas e sujeito à revisão policial.",
        "",
        "## Identificação da ocorrência",
        "",
        f"- ID: `{occurrence['occurrence_id']}`",
        f"- Início: {occurrence['started_at']}",
        f"- Término: {occurrence.get('ended_at', 'não informado')}",
        "",
        "## Linha do tempo",
        "",
    ]
    lines.extend(
        f"- {item['timestamp']} — {item['event']}" for item in timeline
    )
    lines.extend(["", "## Pessoas/interlocutores", ""])
    lines.extend(
        (
            f"- `{speaker['speaker_id']}` — papel provisório: "
            f"{speaker['provisional_role']}; confirmado: {speaker.get('confirmed_role') or 'não'}"
        )
        for speaker in data["speakers"]
    )
    lines.extend(["", "## Declarações relevantes", ""])
    lines.extend(
        f"- `{item['segment_id']}` ({', '.join(item['speaker_ids'])}): {item['raw_transcript']}"
        for item in transcripts
    )
    lines.extend(["", "## Fatos capturados/inferidos", ""])
    lines.extend(
        (
            f"- `{fact['fact_id']}` [{fact['status']}]: {fact['statement']} "
            f"(fontes: {', '.join(fact['source_segments'])})"
        )
        for fact in facts
    )
    lines.extend(["", "## Divergências", ""])
    lines.extend(f"- {json.dumps(item, ensure_ascii=False)}" for item in data["contradictions"])
    if not data["contradictions"]:
        lines.append("- Nenhuma registrada.")
    lines.extend(["", "## Lacunas", ""])
    lines.extend(f"- {json.dumps(item, ensure_ascii=False)}" for item in data["information_gaps"])
    if not data["information_gaps"]:
        lines.append("- Nenhuma registrada.")
    lines.extend(["", "## Hipóteses operacionais", ""])
    lines.extend(
        (
            f"- `{item['hypothesis_id']}` [{item['status']}]: {item['label']} "
            f"(fontes: {', '.join(item['source_segments'])})"
        )
        for item in hypotheses
    )
    lines.extend(["", "## Orientações consultadas e referências", ""])
    for result in guidance:
        for item in result.get("items", []):
            refs = "; ".join(
                f"{source['section']}, p. {source['page']}, chunk {source['chunk_id']}"
                for source in item["sources"]
            )
            lines.append(f"- {item['text']} — {refs}")
    if not guidance:
        lines.append("- Nenhuma orientação consultada.")
    lines.extend(['', '## Providências registradas pelo wearable', ''])
    lines.extend(f"- {event['timestamp']} — {event['action_id']}: {event['status']}" for event in data['guidance_actions'])
    if not data['guidance_actions']:
        lines.append('- Nenhuma providência registrada.')
    lines.extend(["", "## Pendências", ""])
    lines.append(f"- Jobs de processamento pendentes: {len(pending)}")
    lines.extend(["", "## Histórico narrativo preliminar", ""])
    lines.append(data["preliminary_narrative"] or "Nenhum fato consolidado.")
    lines.append("")
    md_path = session_root / "reports" / "HISTORICO_PRELIMINAR.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path
