"""Deterministic local text features used by the DIAO index.

The implementation deliberately avoids network services and model downloads.
The semantic component combines subword hashing with a small, inspectable
Portuguese operational concept map.  It is a retrieval aid, not a legal or
operational reasoning model.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Iterable


SEMANTIC_DIMENSION = 192

STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "essa", "esse", "esta", "este", "foi", "for", "na",
    "nas", "no", "nos", "o", "os", "ou", "para", "pela", "pelas", "pelo",
    "pelos", "por", "que", "se", "sem", "ser", "sua", "suas", "um", "uma",
}

# Every concept is local, explicit and auditable.  Expansions only influence
# ranking; returned guidance is always copied from a source chunk.
CONCEPT_TERMS = {
    "ameaca": {
        "ameaca", "ameacar", "ameacou", "amedrontar", "intimidacao", "intimidar", "mal",
        "medo", "promessa", "gesto", "palavra", "verbal",
    },
    "violencia": {
        "agressao", "agressivas", "arma", "coacao", "forca", "grave", "resistencia",
        "violencia", "violento",
    },
    "subtracao": {
        "furtar", "furto", "levar", "levaram", "levou", "pegaram", "roubar", "roubo",
        "subtraido", "subtracao", "subtrair", "sumiu",
    },
    "patrimonio": {
        "bem", "celular", "coisa", "dinheiro", "objeto", "patrimonio",
        "pertence", "pertences", "telefone", "veiculo",
    },
    "pessoa": {
        "alguem", "autor", "cidadao", "infrator", "pessoa", "solicitante",
        "testemunha", "vitima",
    },
    "flagrante": {"flagrancia", "flagrante", "imediato", "momento"},
    "socorro": {"emergencia", "ferido", "medico", "saude", "socorrer", "urgencia"},
    "prova": {
        "evidencia", "instrumento", "objeto", "pericia", "preservar", "prova",
        "testemunha", "vestigio",
    },
    "registro": {"boletim", "chamada", "ocorrencia", "reds", "registrar", "registro"},
    "homicidio": {"assassinato", "homicidio", "matar", "morte", "tentado", "consumado"},
    "incendio": {"chama", "fogo", "incendio", "queimada"},
    "explosao": {"bomba", "detonacao", "explodir", "explosao"},
    "furto_sem_violencia": {"escondido", "furtar", "furto"},
    "roubo_com_violencia": {"arma", "resistencia", "roubar", "roubo"},
}

TERM_TO_CONCEPTS: dict[str, tuple[str, ...]] = {}
for _concept, _terms in CONCEPT_TERMS.items():
    for _term in _terms:
        TERM_TO_CONCEPTS.setdefault(_term, tuple())
        TERM_TO_CONCEPTS[_term] = tuple(sorted((*TERM_TO_CONCEPTS[_term], _concept)))


def normalize_text(value: str) -> str:
    """Case/accent-fold text while retaining codes and punctuation boundaries."""

    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_marks).strip()


def tokenize(value: str) -> list[str]:
    """Tokenize normalized Portuguese text and keep DIAO code components."""

    tokens = re.findall(r"[a-z0-9]+", normalize_text(value))
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def semantic_feature_counts(value: str) -> Counter[str]:
    """Build transparent lexical, subword and concept features."""

    normalized_value = normalize_text(value)
    tokens = tokenize(value)
    violence_is_negated = bool(
        re.search(r"\bsem\b.{0,30}\b(?:violencia|ameaca|agressao)\b", normalized_value)
    )
    features: Counter[str] = Counter()
    for token in tokens:
        features[f"w:{token}"] += 4.0
        padded = f"^{token}$"
        for size in (3, 4):
            for offset in range(max(0, len(padded) - size + 1)):
                features[f"c:{padded[offset:offset + size]}"] += 0.35
        for concept in TERM_TO_CONCEPTS.get(token, ()):
            if violence_is_negated and concept in {"violencia", "roubo_com_violencia"}:
                continue
            features[f"concept:{concept}"] += 7.0
    for left, right in zip(tokens, tokens[1:]):
        features[f"b:{left}_{right}"] += 2.0

    normalized = " ".join(tokens)
    if violence_is_negated:
        features["concept:furto_sem_violencia"] += 12.0
    if "grave ameaca" in normalized or "mediante violencia" in normalized:
        features["concept:roubo_com_violencia"] += 12.0
    if "mal injusto" in normalized:
        features["concept:ameaca_mal_injusto"] += 12.0
    return features


def nature_hint_scores(value: str) -> dict[str, float]:
    """Return inspectable, source-taxonomy hints for three core incident natures.

    These rules encode the distinctions stated in the DIAO definitions. They
    affect ranking only and can never create guidance text.
    """

    normalized = normalize_text(value)
    tokens = set(tokenize(value))
    concepts = {
        concept
        for token in tokens
        for concept in TERM_TO_CONCEPTS.get(token, ())
    }
    negated_violence = bool(
        re.search(r"\bsem\b.{0,30}\b(?:violencia|ameaca|agressao)\b", normalized)
    )
    has_subtraction = "subtracao" in concepts
    has_property = "patrimonio" in concepts
    has_threat = "ameaca" in concepts
    has_violence = "violencia" in concepts and not negated_violence
    scores: dict[str, float] = {}
    if has_subtraction:
        if negated_violence:
            scores["C01.155"] = 1.0
        elif has_violence or has_threat:
            scores["C01.157"] = 1.0
        elif has_property:
            scores["C01.155"] = 0.85
    if has_threat and not has_subtraction:
        scores["B01.147"] = 1.0
    return scores


def _feature_slot(feature: str, dimension: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    raw = int.from_bytes(digest, "little", signed=False)
    return raw % dimension, -1.0 if raw & (1 << 63) else 1.0


def semantic_vector(value: str, dimension: int = SEMANTIC_DIMENSION) -> list[float]:
    """Create a stable signed feature-hash vector and L2-normalize it."""

    vector = [0.0] * dimension
    for feature, weight in semantic_feature_counts(value).items():
        slot, sign = _feature_slot(feature, dimension)
        vector[slot] += float(weight) * sign
    norm = math.sqrt(sum(component * component for component in vector))
    if norm:
        vector = [component / norm for component in vector]
    return vector


def dot(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
