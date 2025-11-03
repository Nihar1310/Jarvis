import re
from typing import Any, Dict, List

DOC_TYPE_PATTERNS = {
    "PO": r"\b(purchase\s*order|po\s*no\.?|po#)\b",
    "INVOICE": r"\b(invoice\s*no\.?|tax\s*invoice|inv#)\b",
    "DISPATCH": r"\b(dispatch|lr\s*no|e-?way)\b",
    "STOCK_SHEET": r"\b(stock\s*sheet|inventory)\b",
    "QUOTATION": r"\b(quotation|quote|offer|rfq)\b",
    "PAYMENT": r"\b(payment|overdue|reminder)\b",
    "RATE_CIRCULAR": r"\b(rate\s*circular|price\s*list|oa)\b"
}

def classify_doc_type(subject: str, text: str) -> str:
    blob = f"{subject}\n{text}".lower()
    for k, pat in DOC_TYPE_PATTERNS.items():
        if re.search(pat, blob, flags=re.I):
            return k
    return "OTHER"


def normalize_material_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"\(.*?\)", " ", name)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_MATERIAL_STOPWORDS = {
    "bag",
    "bags",
    "mt",
    "metric",
    "ton",
    "tons",
    "kg",
    "kgs",
    "kilo",
    "kilogram",
    "kilograms",
    "of",
    "mm",
    "dia",
    "id",
    "od",
}


def _strip_stopwords(value: str) -> str:
    tokens = [tok for tok in value.split() if tok not in _MATERIAL_STOPWORDS and not tok.isdigit()]
    return " ".join(tokens).strip()


def material_candidate_keys(name: str) -> List[str]:
    base = normalize_material_name(name)
    variants = {base}
    no_stop = _strip_stopwords(base)
    if no_stop:
        variants.add(no_stop)
    return [variant for variant in variants if variant]


def resolve_material_by_alias(raw_name: str, alias_index: Dict[str, Dict[str, Any]]):
    if not raw_name or not alias_index:
        return None

    candidates = material_candidate_keys(raw_name)
    for key in candidates:
        match = alias_index.get(key)
        if match:
            return match

    for key in candidates:
        for alias_key, record in alias_index.items():
            if alias_key and (alias_key in key or key in alias_key):
                return record

    return None
