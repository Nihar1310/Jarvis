import re

from typing import List, Dict

def parse_quote_table_from_text(text: str) -> List[Dict]:
    """
    Heuristic: look for lines with columns roughly matching:
    NO | MATERIAL | QTY | UNIT | RATE | BASIS | HSN
    Works for your current format; refine as needed.
    """
    rows = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        # simple split by multiple spaces / tabs
        parts = re.split(r"\s{2,}|\t", ln)
        if len(parts) >= 5:
            # detect lines with rate-like number and possible HSN code
            if re.search(r"\b\d+(\.\d+)?\b", parts[-1]):  # HSN or amount at end
                rows.append({"raw": parts})
    # TODO: map to (no, material, qty, unit, rate, basis, hsn) with smarter logic
    return rows

def parse_supplier_rate_from_text(text: str) -> list[dict]:
    """
    Extract supplier base rates / OA-add keyword anchoring for known materials: Whytheat, Firecrete, Accoset, etc.
    """
    hits = []
    for mat in ["Whytheat K","Whytheat A","Firecrete Super","Accoset 50","Accmon 70","Accmon 90","Ceramic Blanket"]:
        pat = re.compile(rf"{mat}.*?(\d+(?:\.\d+)?)", re.I)
        for m in pat.finditer(text):
            hits.append({"material": mat, "base_rate": float(m.group(1))})
    return hits

def parse_po_text_naive(text: str) -> dict:
    """
    Use regex to find PO number, vendor, ship-to, and naive line items if available.
    """
    po_no = re.search(r"\bPO\s*(?:No\.?|#)\s*[:\-]?\s*([A-Z0-9\-\/]+)", text, re.I)
    vendor = re.search(r"\bSupplier|Vendor[:\-]\s*(.+)", text, re.I)
    ship_to = re.search(r"\bShip\s*To[:\-]\s*(.+)", text, re.I)
    return {
        "po_number": po_no.group(1) if po_no else None,
        "vendor": vendor.group(1) if vendor else None,
        "ship_to": ship_to.group(1) if ship_to else None,
        "raw_text": text
    }
