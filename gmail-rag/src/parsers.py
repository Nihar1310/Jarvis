import re
from typing import Dict, List, Optional

from .utils import resolve_material_by_alias


_QUOTE_NUMERIC = re.compile(r"^\d+(?:\.\d+)?$")
_HSN_PATTERN = re.compile(r"^\d{4,8}$")


def _clean_number(token: str) -> Optional[float]:
    cleaned = token.replace(",", "")
    return float(cleaned) if _QUOTE_NUMERIC.match(cleaned) else None


def parse_quote_table_from_text(text: str, material_index: Optional[Dict[str, Dict[str, str]]] = None) -> List[Dict]:
    """
    Attempt to parse structured quote rows from OCR/plain text.

    Returns a list of dicts with keys:
    - no, material, material_id, material_canonical
    - qty, unit, rate, basis, hsn
    - raw_line, raw_parts
    """
    rows: List[Dict] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for ln in lines:
        parts = [segment.strip() for segment in re.split(r"\s{2,}|\t", ln) if segment.strip()]
        if len(parts) < 4:
            continue

        tokens = parts.copy()
        entry: Dict[str, Optional[str]] = {"raw_line": ln, "raw_parts": parts}

        # serial number
        entry["no"] = None
        if tokens and re.match(r"^\d+[\.)]?$", tokens[0]):
            no_token = re.sub(r"[^0-9]", "", tokens.pop(0))
            if no_token.isdigit():
                entry["no"] = int(no_token)

        # HSN detection
        entry["hsn"] = None
        if tokens and _HSN_PATTERN.match(tokens[-1]):
            entry["hsn"] = tokens.pop()

        # rate detection (last numeric token)
        entry["rate"] = None
        for idx in range(len(tokens) - 1, -1, -1):
            candidate = _clean_number(tokens[idx])
            if candidate is not None:
                entry["rate"] = candidate
                tokens.pop(idx)
                break

        # basis tokens (FOR/EX/etc.)
        entry["basis"] = None
        basis_idx = None
        for i, token in enumerate(tokens):
            upper = token.upper()
            if upper in {"FOR", "FOB", "CIF", "EX", "EXW", "EX-WORKS", "EXWORKS", "C&F"} or upper.startswith("FOR"):
                basis_idx = i
                break
        if basis_idx is not None:
            entry["basis"] = " ".join(tokens[basis_idx:]).strip()
            tokens = tokens[:basis_idx]

        # quantity and unit (first numeric token and following)
        entry["qty"] = None
        entry["unit"] = None
        for i, token in enumerate(tokens):
            qty_val = _clean_number(token)
            if qty_val is not None:
                entry["qty"] = qty_val
                tokens.pop(i)
                if i < len(tokens):
                    entry["unit"] = tokens.pop(i)
                break

        entry["material"] = " ".join(tokens).strip() or None
        entry["material_id"] = None
        entry["material_canonical"] = None

        if material_index and entry["material"]:
            match = resolve_material_by_alias(entry["material"], material_index)
            if match:
                entry["material_id"] = match["id"]
                entry["material_canonical"] = match["name"]

        rows.append(entry)

    return rows


def parse_supplier_rate_from_text(text: str, material_index: Optional[Dict[str, Dict[str, str]]] = None) -> List[Dict]:
    """
    Extract supplier base rates / OA and map to known materials where possible.
    """
    hits: List[Dict] = []
    for mat in ["Whytheat K", "Whytheat A", "Firecrete Super", "Accoset 50", "Accmon 70", "Accmon 90", "Ceramic Blanket"]:
        pat = re.compile(rf"{mat}.*?(\d+(?:\.\d+)?)", re.I)
        for match in pat.finditer(text):
            record: Dict[str, Optional[str]] = {"material": mat, "base_rate": float(match.group(1))}
            if material_index:
                mapped = resolve_material_by_alias(mat, material_index)
                if mapped:
                    record["material_id"] = mapped["id"]
                    record["material_canonical"] = mapped["name"]
            hits.append(record)
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
