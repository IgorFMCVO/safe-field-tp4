"""Produce repeatable DIAO retrieval metrics for the three acceptance natures."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from operational_guidance.diao.provider import DIAOKnowledgeProvider, GUIDANCE_NOT_SUPPORTED
from operational_guidance.diao.tests.test_diao_retrieval import SCENARIOS


FACTS = {
    "B01.147": "ameaça verbal de mal injusto e grave",
    "C01.155": "telefone subtraído sem ameaça nem violência",
    "C01.157": "telefone subtraído mediante grave ameaça e violência",
}


def evaluate(provider: DIAOKnowledgeProvider) -> dict:
    cases = []
    latencies_ms = []
    stable = 0
    passed = 0
    for expected, variants in SCENARIOS.items():
        for style, query in variants.items():
            runs = []
            for _ in range(3):
                started = time.perf_counter()
                hits = provider.search(query, top_k=5)
                latencies_ms.append((time.perf_counter() - started) * 1000.0)
                runs.append([hit["chunk_id"] for hit in hits])
            sections = [hit["section"]["id"] for hit in provider.search(query, top_k=5)]
            rank = sections.index(expected) + 1 if expected in sections else None
            limit = 5 if style == "ambiguous" else 3
            case_pass = rank is not None and rank <= limit
            passed += int(case_pass)
            is_stable = runs[0] == runs[1] == runs[2]
            stable += int(is_stable)
            cases.append(
                {
                    "expected_section": expected,
                    "style": style,
                    "query": query,
                    "rank": rank,
                    "pass": case_pass,
                    "stable_across_3_runs": is_stable,
                    "top_sections": sections,
                }
            )

    sourced_guidance = 0
    for section, fact in FACTS.items():
        result = provider.retrieve_guidance(
            {"label": section, "nature_code": section, "status": "OFFICER_CONFIRMED"},
            [{"statement": fact}],
        )
        if result["status"] == "SUPPORTED_BY_DIAO" and all(
            action.get("chunk_id") and action.get("section") and action.get("page") and action.get("text")
            for action in result["priority_actions"]
        ):
            sourced_guidance += 1

    blocked = [
        provider.retrieve_guidance(
            {"label": "ROUBO", "status": "PROPOSED"},
            [{"statement": FACTS["C01.157"]}],
        ),
        provider.retrieve_guidance(
            {"label": "fenômeno quântico zxqv sem relação documental", "status": "OFFICER_CONFIRMED"},
            [],
        ),
    ]
    unsupported_guidance = sum(
        1 for result in blocked if result["status"] != GUIDANCE_NOT_SUPPORTED or result["priority_actions"]
    )
    ordered = sorted(latencies_ms)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "status": "PASS" if passed == 15 and stable == 15 and sourced_guidance == 3 and unsupported_guidance == 0 else "FAIL",
        "query_cases_passed": passed,
        "query_cases_total": 15,
        "stable_cases": stable,
        "sourced_guidance_scenarios": sourced_guidance,
        "unsupported_guidance": unsupported_guidance,
        "latency_ms": {
            "median": round(statistics.median(latencies_ms), 3),
            "p95": round(ordered[p95_index], 3),
            "maximum": round(max(latencies_ms), 3),
            "samples": len(latencies_ms),
        },
        "cases": cases,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=repo / "knowledge" / "diao" / "index" / "retrieval_evaluation.json")
    args = parser.parse_args()
    started = time.perf_counter()
    provider = DIAOKnowledgeProvider()
    load_ms = (time.perf_counter() - started) * 1000.0
    result = evaluate(provider)
    result["provider_load_ms"] = round(load_ms, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
