import re

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
