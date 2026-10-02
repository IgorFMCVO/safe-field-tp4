"""Traceable preliminary occurrence history and police-report draft generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .storage import atomic_json
from .identity_review import build_identity_review


OPERATIONAL_FACT_STATUSES = frozenset(
    {"CAPTURED", "SUPPORTED", "OFFICER_CONFIRMED"}
)
PARTIAL_GUIDANCE_STATUSES = frozenset(
    {"GUIDANCE_NOT_AVAILABLE", "GUIDANCE_NOT_SUPPORTED"}
)


def _text(value: object, fallback: str = "não informado") -> str:
    """Render a record field without inventing an operational fact."""
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _speaker_labels(speakers: list[dict]) -> dict[str, str]:
    """Return auditable, role-qualified labels rather than civil identities."""
    labels: dict[str, str] = {}
    for speaker in speakers:
        speaker_id = _text(speaker.get("speaker_id"), "interlocutor não identificado")
        confirmed = speaker.get("confirmed_role")
        provisional = speaker.get("provisional_role")
        if confirmed:
            qualification = f"papel confirmado: {confirmed}"
        elif provisional and provisional != "UNKNOWN":
            qualification = f"papel provisório: {provisional}"
        else:
            qualification = "papel não confirmado"
        labels[speaker_id] = f"{speaker_id} ({qualification})"
    return labels


def _render_timestamp(value: object) -> str:
    if value is None:
        return "momento não informado"
    try:
        return f"{float(value):.2f} s"
    except (TypeError, ValueError):
        return _text(value, "momento não informado")


def _fact_quote(fact: dict) -> str:
    return _text(fact.get("evidence_quote") or fact.get("statement"), "sem transcrição disponível")


def _fact_kind(fact: dict) -> str:
    """Classify provenance, not factual truth or criminal responsibility."""
    if fact.get("negation"):
        return "negação"
    if fact.get("direct_observation"):
        return "observação declarada"
    modality = _text(fact.get("modality"), "").casefold()
    if modality in {"allegation", "reported", "report", "relato", "hearsay"}:
        return "alegação/relato"
    return "declaração"


def _fact_actor_label(fact: dict, labels: dict[str, str]) -> str:
    source_speakers = fact.get("source_speakers") or []
    if source_speakers:
        return ", ".join(labels.get(str(item), str(item)) for item in source_speakers)
    return "interlocutor não identificado"


def _fact_sentence(fact: dict, labels: dict[str, str]) -> str:
    """A concise, neutral chronological sentence tied to an exact quote."""
    actor = _fact_actor_label(fact, labels)
    kind = _fact_kind(fact)
    quote = _fact_quote(fact)
    segments = ", ".join(fact.get("source_segments") or []) or "não informado"
    return (
        f"No marco de {_render_timestamp(fact.get('timestamp'))}, {actor} apresentou "
        f"{kind}: “{quote}” (fontes de áudio: {segments}; status: "
        f"{_text(fact.get('status'))})."
    )


def _hypothesis_label(hypothesis: dict) -> str:
    label = _text(hypothesis.get("label"))
    code = hypothesis.get("nature_code")
    return f"{code} — {label}" if code else label


def _report_model(data: dict) -> dict:
    """Build a review-ready narrative model using only operational records.

    This deliberately preserves attribution and uncertainty.  It is a draft for
    police review, not a finding of criminal responsibility.
    """
    labels = _speaker_labels(data.get("speakers") or [])
    review = data.get("identity_review") or {}
    for speaker_id, identity in review.get("confirmed_identity_by_speaker", {}).items():
        labels[speaker_id] = f"{identity} [identidade conferida pelo policial; {speaker_id}]"
    for sid, decision in review.get("decisions_by_speaker", {}).items():
        if decision.get("role"):
            labels[sid] = labels.get(sid, sid) + f" (papel conferido: {decision['role']})"
    facts = sorted(
        data.get("facts") or [],
        key=lambda item: (
            item.get("timestamp") is None,
            item.get("timestamp") if item.get("timestamp") is not None else 0.0,
            item.get("fact_id", ""),
        ),
    )
    declarations = [fact for fact in facts if not fact.get("negation")]
    denials = [fact for fact in facts if fact.get("negation")]
    confirmed = [
        item
        for item in data.get("hypotheses") or []
        if item.get("status") == "OFFICER_CONFIRMED"
        and item.get("evidence_status") == "OFFICER_CONFIRMED"
    ]
    provisional = [
        item
        for item in data.get("hypotheses") or []
        if item not in confirmed
    ]
    actions = data.get("guidance_actions") or []
    guidance = data.get("guidance") or []
    limitations: list[str] = []
    if data.get("contradictions"):
        limitations.append(
            "Há versões divergentes registradas; a minuta não atribui falsidade "
            "ou responsabilidade a qualquer interlocutor."
        )
    if data.get("information_gaps"):
        limitations.append("Persistem lacunas de informação indicadas pelo processamento.")
    if data.get("error_status"):
        limitations.append("Há indisponibilidades ou pendências técnicas registradas no histórico.")
    excluded = int(data.get("excluded_nonoperational_fact_count") or 0)
    if excluded:
        limitations.append(
            f"{excluded} registro(s) sem status operacional permitido foram excluídos desta minuta."
        )
    if not limitations:
        limitations.append(
            "A minuta permanece sujeita à conferência policial, inclusive quanto a "
            "qualificação, local, data e demais campos administrativos do REDS."
        )
    return {
        "speaker_labels": labels,
        "facts": facts,
        "declarations": declarations,
        "denials": denials,
        "confirmed_hypotheses": confirmed,
        "provisional_hypotheses": provisional,
        "guidance": guidance,
        "guidance_actions": actions,
        "limitations": limitations,
    }


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
    model = _report_model(data)
    facts = model["facts"]
    confirmed_hypotheses = model["confirmed_hypotheses"]

    md_lines = [
        "# BO — RELATO POLICIAL PRELIMINAR PRONTO PARA REVISÃO",
        "",
        "> Minuta não oficial. O conteúdo abaixo usa exclusivamente fatos CAPTURED, "
        "SUPPORTED ou OFFICER_CONFIRMED e permanece sujeito à revisão policial.",
        "",
        "## Validação de participantes",
        "",
        f"- Estado: {data.get('identity_review', {}).get('status', 'REQUIRES_IDENTITY_VALIDATION')}",
        "- Esta é uma minuta; encaminhamento exige revisão explícita no desktop.",
        "",
        "## Identificação para conferência",
        "",
        f"- ID: `{occurrence['occurrence_id']}`",
        f"- Início: {occurrence['started_at']}",
        f"- Término: {occurrence.get('ended_at', 'não informado')}",
        "",
        "## Relato preliminar para revisão e inserção no REDS",
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
        "",
        "RELATO PRELIMINAR PARA REVISAO E INSERCAO NO REDS",
    ]
    if facts:
        opening = (
            "Conforme os registros de áudio e eventos disponíveis nesta ocorrência, "
            "foram consolidadas as declarações abaixo, em ordem cronológica e com "
            "atribuição à respectiva fonte."
        )
        md_lines.extend([opening, ""])
        txt_lines.extend([opening, ""])
        for fact in facts:
            sentence = _fact_sentence(fact, model["speaker_labels"])
            md_lines.append(f"- {sentence}")
            txt_lines.append(f"- {sentence}")
    else:
        md_lines.append("- Nenhum fato com suporte operacional foi consolidado.")
        txt_lines.append("- Nenhum fato com suporte operacional foi consolidado.")

    md_lines.extend(["", "## Pessoas e papéis registrados", ""])
    txt_lines.extend(["", "PESSOAS E PAPEIS REGISTRADOS"])
    if model["speaker_labels"]:
        for speaker_id in sorted(model["speaker_labels"]):
            md_lines.append(f"- {model['speaker_labels'][speaker_id]}")
            txt_lines.append(f"- {model['speaker_labels'][speaker_id]}")
    else:
        md_lines.append("- Nenhum interlocutor registrado.")
        txt_lines.append("- Nenhum interlocutor registrado.")

    md_lines.extend(["", "## Negações e versões divergentes", ""])
    txt_lines.extend(["", "NEGACOES E VERSOES DIVERGENTES"])
    if model["denials"]:
        for fact in model["denials"]:
            sentence = _fact_sentence(fact, model["speaker_labels"])
            md_lines.append(f"- {sentence}")
            txt_lines.append(f"- {sentence}")
    else:
        md_lines.append("- Nenhuma negação estruturada foi registrada nos fatos consolidados.")
        txt_lines.append("- Nenhuma negacao estruturada foi registrada nos fatos consolidados.")
    for contradiction in data.get("contradictions") or []:
        identifier = _text(contradiction.get("contradiction_id"), "divergência sem identificador")
        sources = ", ".join(contradiction.get("segment_ids") or []) or "fontes não informadas"
        rendered = (
            f"Divergência registrada ({identifier}; fontes: {sources}). "
            "Não há atribuição de falsidade nesta minuta."
        )
        md_lines.append(f"- {rendered}")
        txt_lines.append(f"- {rendered}")

    md_lines.extend(["", "## Hipótese operacional", ""])
    txt_lines.extend(["", "HIPOTESE OPERACIONAL"])
    if confirmed_hypotheses:
        for hypothesis in confirmed_hypotheses:
            rendered = _hypothesis_label(hypothesis)
            source_segments = ", ".join(hypothesis.get("source_segments") or [])
            line = (
                f"Hipótese confirmada pelo policial: {rendered} "
                f"(ID: {hypothesis['hypothesis_id']}; fontes: {source_segments})."
            )
            md_lines.append(f"- {line}")
            txt_lines.append(f"- {line}")
    else:
        md_lines.append("- Nenhuma hipótese operacional foi confirmada pelo policial.")
        txt_lines.append("- Nenhuma hipotese operacional foi confirmada pelo policial.")
    for hypothesis in model["provisional_hypotheses"]:
        line = (
            f"Hipótese ainda não confirmada: {_hypothesis_label(hypothesis)} "
            f"(ID: {_text(hypothesis.get('hypothesis_id'))}; status: "
            f"{_text(hypothesis.get('status'))})."
        )
        md_lines.append(f"- {line}")
        txt_lines.append(f"- {line}")

    md_lines.extend(["", "## Orientações e providências efetivamente registradas", ""])
    txt_lines.extend(["", "ORIENTACOES E PROVIDENCIAS EFETIVAMENTE REGISTRADAS"])
    if model["guidance"]:
        for result in model["guidance"]:
            for item in result.get("items") or []:
                # Guidance is a consulted source, never evidence that an action occurred.
                md_lines.append(f"- Orientação disponibilizada: {_text(item.get('text'))}")
                txt_lines.append(f"- Orientacao disponibilizada: {_text(item.get('text'))}")
    else:
        md_lines.append("- Nenhuma orientação foi disponibilizada no registro.")
        txt_lines.append("- Nenhuma orientacao foi disponibilizada no registro.")
    if model["guidance_actions"]:
        for action in model["guidance_actions"]:
            line = (
                f"Providência registrada no wearable: ação {_text(action.get('action_id'))}, "
                f"status {_text(action.get('status'))}, em {_text(action.get('timestamp'))}."
            )
            md_lines.append(f"- {line}")
            txt_lines.append(f"- {line}")
    else:
        md_lines.append("- Nenhuma providência foi marcada como executada no wearable.")
        txt_lines.append("- Nenhuma providencia foi marcada como executada no wearable.")

    md_lines.extend(["", "## Limitações para revisão policial", ""])
    txt_lines.extend(["", "LIMITACOES PARA REVISAO POLICIAL"])
    for limitation in model["limitations"]:
        md_lines.append(f"- {limitation}")
        txt_lines.append(f"- {limitation}")

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
    history_status = "PARTIAL" if error_status else "COMPLETE"

    data = {
        "document_type": "HISTORICO_PRELIMINAR",
        "identity_review": build_identity_review(session_root),
        "history_status": history_status,
        "disclaimer": "Conteúdo preliminar, rastreável às fontes capturadas e sujeito à revisão policial.",
        "occurrence": occurrence,
        "timeline": timeline,
        "speakers": speakers_doc.get("speakers", []),
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
    # Keep the rendering inputs alongside the immutable source records.  This
    # lets a reviewer audit why a sentence was included without promoting an
    # allegation or a rejected candidate to an operational fact.
    data["police_report_model"] = _report_model(data)
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
