import os, json

from fastapi import FastAPI, Query
from dotenv import load_dotenv
from sqlalchemy import text
from jinja2 import Template

from .storage import db, init_schema, rows, row
from .gmail_sync import sync_recent
from .ocr_vision import upload_to_gcs, ocr_pdf_to_text_gcs, ocr_image_local
from .parsers import parse_quote_table_from_text, parse_supplier_rate_from_text, parse_po_text_naive
from .recommend import suggest_rate

load_dotenv()

app = FastAPI()

@app.on_event("startup")
def _startup():
    init_schema()

@app.post("/sync")
def sync():
    """Fetch recent Gmail, store emails, download attachments. OCR pass is manual via /ocr for now."""
    report = sync_recent()
    return report

@app.post("/ocr")
def ocr_attachment(local_path: str, is_pdf: bool = True):
    """Upload to GCS and OCR to text, then naive PO parse as demo."""
    if is_pdf:
        gcs_uri = upload_to_gcs(local_path, os.path.basename(local_path))
        text_body = ocr_pdf_to_text_gcs(gcs_uri)
    else:
        text_body = ocr_image_local(local_path)
    po = parse_po_text_naive(text_body)
    return {"text_preview": text_body[:1200], "po_extract": po}

@app.get("/price-memory/context")
def price_memory_context(customer: str, material: str, days: int = 90, region: str | None = None):
    cx = db().connect()
    cid = row(cx, "SELECT id, region FROM customers WHERE name=:n", {"n":customer})
    mid = row(cx, "SELECT id FROM materials WHERE name=:n OR (aliases IS NOT NULL AND aliases LIKE :a)", {"n":material, "a":f"%{material}%"})
    if not cid or not mid: return {"error":"customer/material not found"}
    last = row(cx, """
      SELECT rate, basis, freight, cd_pct, date_ts, gmail_id FROM quotes
      WHERE customer_id=:cid AND material_id=:mid
      ORDER BY date_ts DESC LIMIT 1
    """, {"cid":cid.id, "mid":mid.id})
    region_val = region or cid.region
    band = row(cx, """
      WITH r AS (
        SELECT q.rate FROM quotes q
        JOIN customers c ON c.id=q.customer_id
        WHERE q.material_id=:mid AND c.region=:r AND q.date_ts >= date('now', :ago)
      )
      SELECT
        (SELECT rate FROM r ORDER BY rate LIMIT 1 OFFSET CAST((0.50 * (SELECT count(*) FROM r)) AS INT)) AS p50,
        (SELECT rate FROM r ORDER BY rate LIMIT 1 OFFSET CAST((0.90 * (SELECT count(*) FROM r)) AS INT)) AS p90,
        (SELECT count(*) FROM r) AS sample
    """, {"mid":mid.id, "r":region_val, "ago": f"-{days} day"})
    # naive supplier base: pick latest supplier_rates row
    sup = row(cx, """
      SELECT base_rate, stockist_discount_pct, cash_discount_pct, effective_date, source_gmail_id
      FROM supplier_rates WHERE material_id=:mid ORDER BY effective_date DESC LIMIT 1
    """, {"mid":mid.id})
    # for demo: net_base_plus_freight = base_rate * (1 - disc%) + (freight or 0)
    net_base = (sup.base_rate * (1 - (sup.stockist_discount_pct or 0)/100.0)) if sup else None
    result = {
      "last_to_customer": ({"rate": last.rate, "date": last.date_ts, "basis": last.basis, "gmail_link": f"https://mail.google.com/mail/#all/{last.gmail_id}"} if last else None),
      "recent_band": {"p50": band.p50 if band else None, "p90": band.p90 if band else None, "sample": band.sample if band else 0, "days": days},
      "supplier_base": ({"net_base": net_base, "disc": sup.stockist_discount_pct, "cd": sup.cash_discount_pct, "effective": sup.effective_date, "source_link": f"https://mail.google.com/mail/#all/{sup.source_gmail_id}"} if sup else None)
    }
    cx.close()
    return result

@app.get("/recommend")
def recommend(customer: str, material: str, basis: str | None = None, qty: float | None = None, min_margin_pct: float = 18.0):
    ctx = price_memory_context(customer, material)
    if "error" in ctx: return ctx
    last_rate = ctx["last_to_customer"]["rate"] if ctx["last_to_customer"] else None
    band_p50 = ctx["recent_band"]["p50"]
    band_p90 = ctx["recent_band"]["p90"]
    net_base_plus_freight = (ctx["supplier_base"]["net_base"] if ctx["supplier_base"] else None)
    suggested, floor, warns = suggest_rate(net_base_plus_freight, last_rate, band_p50, band_p90, min_margin_pct)
    return {
      "suggested": {"rate": suggested, "min_margin_floor": floor},
      "rationale": [
        ">= margin floor over supplier net+freight" if floor else "no supplier base",
        "within last-90d band" if (band_p50 and band_p90) else "no recent band available"
      ],
      "warnings": warns,
      "context": ctx
    }

# -------- Quotation Maker: HTML + Monospace --------------
HTML_TEMPLATE = """
<!doctype html><html><body style="font-family:Arial,sans-serif;color:#111;">
<h3 style="margin:0 0 8px 0;">QUOTATION</h3>
<div style="font-size:12px;color:#666;">Date: {{quote_date}}</div>
<p>{{attention}}</p>
<p>{{intro}}</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
  <tr><th>NO</th><th>MATERIAL</th><th>QTY</th><th>UNIT</th><th>RATE RS./UNIT</th><th>EX WORK / BASIS</th><th>HSN CODE</th></tr>
  {% for r in items %}
  <tr>
    <td>{{r.no}}</td><td>{{r.material}}</td><td>{{r.qty}}</td><td>{{r.unit}}</td>
    <td><b>{{r.rate}}</b></td><td>{{r.basis}}</td><td>{{r.hsn}}</td>
  </tr>
  {% endfor %}
</table>
<p><b>The above rates are Ex our Work / Godown, as above mentioned.</b><br/>
<b>TAXES:</b> {{taxes}}<br/>
<b>DELIVERY:</b> {{delivery}}<br/>
<b>PAYMENT:</b> {{payment}}<br/>
<b>FREIGHT:</b> {{freight}}</p>
<p>Warm Regards,<br/>{{signatory}}<br/>{{phone}}</p>
</body></html>
"""

def monospace_table(items):
    cols = ["NO","MATERIAL","QTY","UNIT","RATE RS./UNIT","EX WORK / BASIS","HSN CODE"]
    # compute widths
    def w(col):
        base = len(col)
        for r in items:
            base = max(base, len(str(r.get(col.lower().replace(" ","_").replace("/","").replace(".",""), ""))))
        return base
    widths = {c: max(len(c), 8) for c in cols}
    header = " ".join(f"{c:<{widths[c]}}" for c in cols)
    sep = " ".join("-"*widths[c] for c in cols)
    rows_txt = []
    for r in items:
        row_map = {
            "NO": r["no"], "MATERIAL": r["material"], "QTY": r["qty"], "UNIT": r["unit"],
            "RATE RS./UNIT": r["rate"], "EX WORK / BASIS": r["basis"], "HSN CODE": r["hsn"]
        }
        rows_txt.append(" ".join(f"{str(row_map[c]):<{widths[c]}}" for c in cols))
    return header + "\n" + sep + "\n" + "\n".join(rows_txt)

@app.post("/quote/create")
def quote_create(payload: dict):
    """
    payload:
    {
      "customer":"Electrotherm",
      "quote_date":"03-11-2025",
      "items":[{"no":1,"material":"Whytheat K (Bag of 25 Kg)","qty":1000,"unit":"KG","rate":1610,"basis":"FOR Ahmedabad","hsn":"3816"}],
      "taxes":"18% GST extra","delivery":"Ready stock, subject to prior sale","payment":"7 days",
      "freight":"Inclusive (Unloading in your scope)","signatory":"Gaurav Shukla","phone":"+91 9727756470"
    }
    """
    tmpl = Template(HTML_TEMPLATE)
    html = tmpl.render(
        quote_date=payload.get("quote_date"),
        attention=f"Dear {payload.get('customer')},",
        intro="We thank you for your inquiry; please find our offer below.",
        items=payload["items"],
        taxes=payload.get("taxes","Applicable GST will be charged extra."),
        delivery=payload.get("delivery","After 7 days."),
        payment=payload.get("payment","7 Days"),
        freight=payload.get("freight","Extra at actual (Unloading in your scope)."),
        signatory=payload.get("signatory","Anuj Traders"),
        phone=payload.get("phone","")
    )
    copy_block = monospace_table(payload["items"])
    subject = f"QUOTATION - {payload.get('customer')} - {payload.get('quote_date')}"
    return {"gmail_subject": subject, "gmail_html": html, "copy_block_text": copy_block}
