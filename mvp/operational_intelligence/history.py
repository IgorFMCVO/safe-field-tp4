"""Traceable preliminary occurrence history and police-report draft generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .identity_review import build_identity_review
from .storage import atomic_json


OPERATIONAL_FACT_STATUSES = frozenset(
    {"CAPTURED", "SUPPORTED", "OFFICER_CONFIRMED"}
)
PARTIAL_GUIDANCE_STATUSES = frozenset(
    {"GUIDANCE_NOT_AVAILABLE", "GUIDANCE_NOT_SUPPORTED"}
)


def _load_json_files(paths: Iterable[Path]) -> list[dict]:
    result = []
    for path in sorted(paths):
        result.append(json.loads(path.read_text(encoding="utf-8")))
    return result


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _is_operational_fact(fact: dict) -> bool:
    return str(fact.get("status", "")).upper() in OPERATIONAL_FACT_STATUSES


def _filtered_fact_graph(fact_graph: dict, allowed_fact_ids: set[str]) -> dict:
    return {
        **fact_graph,
        "facts": [
            fact
            for fact in fact_graph.get("facts", [])
            if _is_operational_fact(fact) and fact.get("fact_id") in allowed_fact_ids
        ],
        "relations": [
            relation
            for relation in fact_graph.get("relations", [])
            if relation.get("source_fact") in allowed_fact_ids
            and relation.get("target_fact") in allowed_fact_ids
        ],
    }


def _history_errors(pending: list[dict], guidance: list[dict]) -> list[dict]:
    errors = [
        {
            "source": "PROCESSING",
            "kind": item.get("kind"),
            "identifier": (
                item.get("hypothesis_id")
                or (item.get("metadata") or {}).get("segment_id")
            ),
            "status": item.get("status"),
            "error_type": item.get("error_type"),
            "error": item.get("error"),
        }
        for item in pending
    ]
    errors.extend(
        {
            "source": "GUIDANCE",
            "hypothesis_id": item.get("hypothesis_id"),
            "status": item.get("status"),
            "error_type": item.get("error_type"),
            "error": item.get("error"),
        }
        for item in guidance
        if item.get("status") in PARTIAL_GUIDANCE_STATUSES
    )
    return errors


def _build_police_report_draft(session_root: Path, data: dict) -> tuple[Path, Path]:
    occurrence = data["occurrence"]
    facts = sorted(
        data["facts"],
        key=lambda item: (
            item.get("timestamp") is None,
            item.get("timestamp") or 0.0,
            item.get("fact_id", ""),
        ),
    )
    identity_review = data.get("identity_review") or {}
    confirmed_identity = identity_review.get("confirmed_identity_by_speaker", {})

    def speaker_label(speaker_id: str) -> str:
        identity = confirmed_identity.get(speaker_id)
        return f"{identity} [OFFICER_CONFIRMED]" if identity else speaker_id

    confirmed_hypotheses = [
        item
        for item in data["hypotheses"]
        if item.get("status") == "OFFICER_CONFIRMED"
        and item.get("evidence_status") == "OFFICER_CONFIRMED"
    ]

    md_lines = [
        "# BO — RELATO POLICIAL PRELIMINAR PRONTO PARA REVISÃO",
        "",
        "> Minuta não oficial. O conteúdo abaixo usa exclusivamente fatos CAPTURED, "
        "SUPPORTED ou OFFICER_CONFIRMED e permanece sujeito à revisão policial.",
        "",
        "## Ocorrência",
        "",
        f"- ID: `{occurrence['occurrence_id']}`",
        f"- Início: {occurrence['started_at']}",
        f"- Término: {occurrence.get('ended_at', 'não informado')}",
        f"- Validação de identidade: `{identity_review.get('status', 'VALIDATED_OR_NOT_REQUIRED')}`",
        f"- REDS final: `{'LIBERADO' if identity_review.get('report_finalization_allowed', True) else 'AGUARDA VALIDACAO DE IDENTIDADE'}`",
        "",
        "## Relato cronológico sustentado",
        "",
    ]
    txt_lines = [
        "BO - RELATO POLICIAL PRELIMINAR PRONTO PARA REVISAO",
        "",
        "Minuta nao oficial. Usa exclusivamente fatos CAPTURED, SUPPORTED ou "
        "OFFICER_CONFIRMED e permanece sujeita a revisao policial.",
        "",
        f"Ocorrencia: {occurrence['occurrence_id']}",
        f"Inicio: {occurrence['started_at']}",
        f"Termino: {occurrence.get('ended_at', 'nao informado')}",
        f"Validacao de identidade: {identity_review.get('status', 'VALIDATED_OR_NOT_REQUIRED')}",
        f"REDS final: {'LIBERADO' if identity_review.get('report_finalization_allowed', True) else 'AGUARDA VALIDACAO DE IDENTIDADE'}",
        "",
        "RELATO CRONOLOGICO SUSTENTADO",
    ]
    if facts:
        for fact in facts:
            timestamp = (
                f"{float(fact['timestamp']):.2f} s"
                if fact.get("timestamp") is not None
                else "tempo não informado"
            )
            speakers = ", ".join(
                speaker_label(item)
                for item in (fact.get("source_speakers") or ["interlocutor não identificado"])
            )
            segments = ", ".join(fact.get("source_segments") or [])
            quote = fact.get("evidence_quote") or fact.get("statement") or ""
            status = fact.get("status", "")
            md_lines.append(
                f"- {timestamp} — `{speakers}`: “{quote}” "
                f"[`{status}`; fontes: {segments}]"
            )
            txt_lines.append(
                f"- {timestamp} - {speakers}: \"{quote}\" "
                f"[{status}; fontes: {segments}]"
            )
    else:
        md_lines.append("- Nenhum fato com suporte operacional foi consolidado.")
        txt_lines.append("- Nenhum fato com suporte operacional foi consolidado.")

    md_lines.extend(["", "## Hipótese confirmada", ""])
    txt_lines.extend(["", "HIPOTESE CONFIRMADA"])
    if confirmed_hypotheses:
        for hypothesis in confirmed_hypotheses:
            code = hypothesis.get("nature_code")
            label = hypothesis.get("label") or "não informada"
            rendered = f"{code} — {label}" if code else label
            md_lines.append(f"- `{hypothesis['hypothesis_id']}`: {rendered}")
            txt_lines.append(f"- {hypothesis['hypothesis_id']}: {rendered}")
    else:
        md_lines.append("- Nenhuma hipótese operacional confirmada.")
        txt_lines.append("- Nenhuma hipotese operacional confirmada.")

    md_lines.extend(
        [
            "",
            "## Estado de processamento",
            "",
            f"- Histórico: `{data['history_status']}`",
            f"- Erros/indisponibilidades registrados: {len(data['error_status'])}",
            "",
        ]
    )
    txt_lines.extend(
        [
            "",
            "ESTADO DE PROCESSAMENTO",
            f"- Historico: {data['history_status']}",
            f"- Erros/indisponibilidades registrados: {len(data['error_status'])}",
            "",
        ]
    )
    md_path = session_root / "reports" / "BO_RELATO_POLICIAL_PRONTO.md"
    txt_path = session_root / "reports" / "BO_RELATO_POLICIAL_PRONTO.txt"
    _write_text_atomic(md_path, "\n".join(md_lines))
    _write_text_atomic(txt_path, "\n".join(txt_lines))
    return md_path, txt_path


def build_preliminary_history(session_root: Path) -> tuple[Path, Path]:
    occurrence = json.loads((session_root / "occurrence.json").read_text(encoding="utf-8"))
    timeline = [
        json.loads(line)
        for line in (session_root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    speakers_doc = json.loads(
        (session_root / "speakers" / "registry.json").read_text(encoding="utf-8")
    )
    transcripts = _load_json_files((session_root / "transcripts").glob("segment_*.json"))
    # Diagnostic sidecars (candidate verification, event graph, taxonomy
    # screening) deliberately share the session tree, but they are not domain
    # records.  Load only typed artifact filenames so closeout remains stable
    # as new auditable sidecars are added.
    all_facts = _load_json_files(
        path
        for path in (session_root / "facts").glob("*.json")
        if path.name.startswith("FACT_")
    )
    facts = [fact for fact in all_facts if _is_operational_fact(fact)]
    analyses = _load_json_files((session_root / "facts").glob("analysis_*.json"))
    hypotheses = _load_json_files(
        path
        for path in (session_root / "hypotheses").glob("*.json")
        if path.name.startswith("HYP_")
    )
    guidance = _load_json_files(
        path
        for path in (session_root / "guidance").glob("*.json")
        if path.name.startswith("HYP_")
    )
    pending = _load_json_files((session_root / "jobs").glob("pending_*.json"))
    fact_graph_path = session_root / "facts" / "fact_graph.json"
    fact_graph = json.loads(fact_graph_path.read_text(encoding="utf-8"))
    allowed_fact_ids = {fact["fact_id"] for fact in facts}
    fact_graph = _filtered_fact_graph(fact_graph, allowed_fact_ids)
    watch_path = session_root / "watch_events.jsonl"
    watch_events = (
        [
            json.loads(line)
            for line in watch_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if watch_path.exists()
        else []
    )
    error_status = _history_errors(pending, guidance)
    identity_review = build_identity_review(session_root)
    if identity_review.get("pending_count", 0):
        error_status.append(
            {
                "code": "IDENTITY_VALIDATION_REQUIRED",
                "detail": "Atribuição de identidade requer confirmação humana antes do REDS final.",
                "pending_count": identity_review["pending_count"],
            }
        )
    history_status = "PARTIAL" if error_status else "COMPLETE"

    data = {
        "document_type": "HISTORICO_PRELIMINAR",
        "history_status": history_status,
        "disclaimer": "Conteúdo preliminar, rastreável às fontes capturadas e sujeito à revisão policial.",
        "occurrence": occurrence,
        "timeline": timeline,
        "speakers": speakers_doc.get("speakers", []),
        "identity_review": identity_review,
        "transcripts": transcripts,
        "facts": facts,
        "excluded_nonoperational_fact_count": len(all_facts) - len(facts),
        "fact_graph": fact_graph,
        "contradictions": [
            item for analysis in analyses for item in analysis.get("contradictions", [])
        ],
        "information_gaps": [
            item for analysis in analyses for item in analysis.get("information_gaps", [])
        ],
        "hypotheses": hypotheses,
        "officer_decisions": [
            item for item in timeline if item["event"] == "HYPOTHESIS_OFFICER_DECISION"
        ],
        "guidance": guidance,
        "guidance_statuses": [
            {
                "hypothesis_id": item.get("hypothesis_id"),
                "status": item.get(
                    "status", "SUPPORTED" if item.get("items") else "NOT_REQUESTED"
                ),
            }
            for item in guidance
        ],
        "watch_events": watch_events,
        "guidance_actions": [
            event for event in watch_events if event.get("action") == "ACTION_STATUS"
        ],
        "pending_processing": pending,
        "error_status": error_status,
        # Narrative includes only facts with an operationally permitted status.
        "preliminary_narrative": " ".join(fact.get("statement", "") for fact in facts),
    }
    json_path = session_root / "reports" / "HISTORICO_PRELIMINAR.json"
    atomic_json(json_path, data)

    lines = [
        "# HISTÓRICO PRELIMINAR",
        "",
        "> Conteúdo preliminar, rastreável às fontes capturadas e sujeito à revisão policial.",
        "",
        f"- Estado do histórico: `{history_status}`",
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
    lines.extend(f"- {item['timestamp']} — {item['event']}" for item in timeline)
    lines.extend(["", "## Pessoas/interlocutores", ""])
    identity_map = identity_review.get("confirmed_identity_by_speaker", {})
    lines.extend(
        (
            f"- `{speaker['speaker_id']}` — papel provisório: "
            f"{speaker['provisional_role']}; papel confirmado: {speaker.get('confirmed_role') or 'não'}; "
            f"identidade confirmada: {identity_map.get(speaker['speaker_id'], 'não')}"
        )
        for speaker in data["speakers"]
    )
    if identity_review.get("pending_count", 0):
        lines.append(
            f"- ⚠ {identity_review['pending_count']} atribuição(ões) aguardam validação no desktop antes do REDS final."
        )
    lines.extend(["", "## Declarações relevantes", ""])
    lines.extend(
        f"- `{item['segment_id']}` ({', '.join(item['speaker_ids'])}): {item['raw_transcript']}"
        for item in transcripts
    )
    lines.extend(["", "## Fatos operacionais sustentados", ""])
    lines.extend(
        (
            f"- `{fact['fact_id']}` [{fact['status']}]: {fact['statement']} "
            f"(fontes: {', '.join(fact['source_segments'])})"
        )
        for fact in facts
    )
    if not facts:
        lines.append("- Nenhum fato com status operacional permitido.")
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
    if not hypotheses:
        lines.append("- Nenhuma hipótese registrada.")
    lines.extend(["", "## Orientações consultadas e referências", ""])
    for result in guidance:
        items = result.get("items", [])
        if not items:
            lines.append(
                f"- `{result.get('hypothesis_id', 'não informado')}`: "
                f"`{result.get('status', 'GUIDANCE_NOT_AVAILABLE')}`."
            )
        for item in items:
            refs = "; ".join(
                f"{source['section']}, p. {source['page']}, chunk {source['chunk_id']}"
                for source in item["sources"]
            )
            lines.append(f"- {item['text']} — {refs}")
    if not guidance:
        lines.append("- Nenhuma orientação consultada.")
    lines.extend(["", "## Providências registradas pelo wearable", ""])
    lines.extend(
        f"- {event['timestamp']} — {event['action_id']}: {event['status']}"
        for event in data["guidance_actions"]
    )
    if not data["guidance_actions"]:
        lines.append("- Nenhuma providência registrada.")
    lines.extend(["", "## Pendências e erros", ""])
    lines.append(f"- Jobs de processamento pendentes: {len(pending)}")
    for error in error_status:
        identifier = error.get("identifier") or error.get("hypothesis_id") or "não informado"
        lines.append(
            f"- `{identifier}` — `{error.get('status')}`: "
            f"{error.get('error') or error.get('error_type') or 'indisponibilidade registrada'}"
        )
    lines.extend(["", "## Histórico narrativo preliminar", ""])
    lines.append(data["preliminary_narrative"] or "Nenhum fato consolidado.")
    lines.append("")
    md_path = session_root / "reports" / "HISTORICO_PRELIMINAR.md"
    _write_text_atomic(md_path, "\n".join(lines))
    _build_police_report_draft(session_root, data)
    return md_path, json_path
