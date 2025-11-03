# Anuj Traders Jarvis

Anuj Traders Jarvis is an email-aware pricing intelligence and quotation service designed to help the Anuj Traders sales desk move faster when responding to customer inquiries. It continuously ingests business correspondence from Gmail, extracts structured commercial data, and surfaces actionable guidance for quotations, negotiating guardrails, and purchase order review.

## Why Jarvis matters

Anuj Traders receives hundreds of procurement-mails that include customer quotes, purchase orders (POs), supplier rate circulars, and stock updates. This information lives in Gmail threads and file attachments, forcing the team to manually search for the last price offered, hunt for the current supplier OA rate, and rebuild quotation tables by hand. Jarvis centralises that workflow so the team can:

- Track the most recent price quoted to any customer-material combination with provenance back to the Gmail message.
- Pull supplier base rates, discounts, and OA terms for each refractory product to understand minimum margin guardrails before issuing a quote.
- Generate price recommendations that respect historical bands and margin rules while alerting the team if a proposed rate is below prior deals.
- OCR supplier circulars and purchase-order PDFs/images using Google Cloud Vision to turn unstructured attachments into searchable, auditable text.
- Produce Gmail-ready quotation emails?including HTML tables and monospaced copy blocks?in a single API call.
- Catch up on daily actionable emails (quotes, POs, invoices, payments) without combing through the entire inbox.

## High-level architecture

```
Gmail (OAuth read-only) ---> Jarvis Sync (/sync) ---> SQLite/ Postgres (price_memory.db)
                                          |            |
                                          |            +--> Structured tables: emails, quotes, supplier_rates, purchase_orders, po_lines
                                          |
                                          +--> Attachments stored in data/attachments

Attachments ---> Google Cloud Storage ---> Google Cloud Vision OCR ---> Text parsing (POs, quotes, supplier OA)

FastAPI Endpoints ---> Pricing recommendations / quotation builder / context APIs
```

Key components:

- **FastAPI backend (`src/main.py`)** bootstraps the service, initialises the database schema, and exposes operational endpoints.
- **Gmail ingestion (`src/gmail_sync.py`)** handles OAuth credential refresh, pulls recent business messages, and stores metadata + attachments.
- **Storage helpers (`src/storage.py`)** manage the SQLAlchemy engine, schema initialisation, base query utilities, and material alias indexing.
- **Utilities (`src/utils.py`)** include document classification patterns and material normalisation/alias resolution.
- **OCR integration (`src/ocr_vision.py`)** uploads PDFs/images to Google Cloud Storage and leverages Google Cloud Vision (async for PDFs, sync for images) to extract text.
- **Parsers (`src/parsers.py`)** convert OCR/plain text into structured rows for quotations, supplier rate circulars, and purchase orders.
- **Recommendation engine (`src/recommend.py`)** provides pricing guardrail calculations and summarises warnings.

## Core workflows

### 1. Email sync and extraction

1. `POST /sync`
   - Uses Gmail read-only OAuth to fetch the last ~48 hours of business emails that match quotation/PO/invoice keywords.
   - Persists email headers, body text, doc type classification, and a Gmail permalink in the `emails` table.
   - Downloads attachments (PDF/Images) into `data/attachments/` for downstream OCR.

2. `POST /ocr`
   - Accepts a local attachment path and determines if it should run PDF (async) or image (sync) OCR.
   - Uploads the file to Google Cloud Storage before invoking Google Cloud Vision.
   - Returns extracted text and a naive purchase-order summary. Future iterations are expected to persist PO metadata into `purchase_orders` and `po_lines`.

### 2. Price memory and recommendations

1. `GET /price-memory/context`
   - Looks up the requested customer and material, resolving aliases via the material index.
   - Returns the last quote issued (rate, basis, Gmail link), the regional price band (p50/p90) over the past N days, and the latest supplier base rate.

2. `GET /recommend`
   - Combines supplier net Base+Freight, recent band percentiles, and the last customer rate to deliver a suggested quote rate.
   - Highlights whether the proposed number clears minimum margin floors or slips beneath recent deal history, producing warnings when needed.

### 3. Quote generation

`POST /quote/create`

- Accepts structured line items (material, qty, unit, rate, basis, HSN) with meta fields such as taxes, delivery, payment, freight, signatory.
- Returns
  - Gmail subject in the format `QUOTATION - <Customer> - <Date>`
  - HTML snippet ready to paste into Gmail compose (table + narrative text)
  - Monospaced text block for messaging platforms that do not accept HTML.

### 4. Material alias resolution

- `storage.load_material_alias_index()` builds a lookup table from `materials` using canonical names and JSON-encoded aliases.
- `utils.resolve_material_by_alias()` normalises incoming text (removing bag sizes, units, etc.) and matches against the alias index.
- `parsers.parse_quote_table_from_text()` and `parse_supplier_rate_from_text()` call the resolver to attach `material_id` and canonical names to parsed rows, ensuring consistent analytics even when customers refer to products using different shorthands.

## Data model summary

- `customers`: Known buyers, including region and tier metadata for price band calculations.
- `materials`: Master list of SKUs (name, grade, optional alias JSON array) used for alias resolution.
- `emails`: All synced Gmail messages with classification, direction (incoming/outgoing), and Gmail URL.
- `quotes`: Parsed quotation line items referencing `emails` via `gmail_id` plus commercial attributes like rate, basis, discounts, and confidence.
- `supplier_rates`: Supplier OA / stockist rates with discount percentages and freight info.
- `purchase_orders` & `po_lines`: PO metadata and line items, designed to capture OCR-parsed PDF content.

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Environment variables live in `.env`; example values are already provided (replace with real credentials/secrets):

- Gmail OAuth Client ID/Secret (readonly scope)
- Google Cloud Vision project + bucket + service-account key
- Database URL (SQLite local by default, Postgres for production)
- Chroma directory (future vector search capability)
- App host/port

## API quick reference (MVP)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/sync` | POST | Pull recent Gmail business emails, store metadata, download attachments |
| `/ocr` | POST | OCR a local attachment path via Google Cloud Vision and return parsed PO preview |
| `/price-memory/context` | GET | Retrieve last quote, price band, supplier base for a customer/material |
| `/recommend` | GET | Suggest a quote rate with guardrails and context |
| `/quote/create` | POST | Generate Gmail-ready quotation HTML + monospaced copy block |

## Implementation notes & roadmap

- OCR: PDF OCR is asynchronous (Vision batch annotate) and depends on Google Cloud Storage; ensure `GOOGLE_APPLICATION_CREDENTIALS` points to a valid service-account JSON.
- Alias matching: Current matching works best with curated alias lists (`materials.aliases`). Consider adding fuzzy search or phonetic matching for noisy OCR results.
- Pricing bands: For SQLite, percentile approximations rely on ordered offsets; migrating to Postgres allows native percentile functions.
- Supplier circulars: Extend `parse_supplier_rate_from_text()` to process OCR output beyond the current static keywords.
- Review queue: Persist parser confidence scores in `quotes.parsed_confidence` to drive manual verification workflows.
- Security: Add API authentication (token or OAuth) before exposing endpoints outside the internal network.
- Frontend: A Next.js dashboard can call the FastAPI endpoints for quote creation, context retrieval, and daily catch-up views.

## Contributing & operations

- The project expects Python 3.11+.
- Run `uvicorn src.main:app --reload` during development to auto-reload on code changes.
- Ensure `.env` and OAuth token directories remain private (`data/tokens/`).
- Attachments downloaded from Gmail reside in `data/attachments/`; periodically prune for storage hygiene or move to GCS long-term.
- When deploying to production, switch from SQLite to Postgres by updating `DB_URL` and running `init_schema()` to migrate the schema.

## Support

For operational issues (OAuth refresh errors, OCR quota, database tuning), contact the Anuj Traders operations team or the developer responsible for Jarvis. Keep note of:

- Gmail API quota usage (watch for HTTP 429/403 errors in logs).
- Google Cloud Vision billing status and service account permissions.
- Database growth?consider pruning stale email bodies or moving to partitioned tables over time.

Anuj Traders Jarvis turns Gmail traffic into pricing intelligence so the sales desk can focus on negotiations rather than digging through inboxes.
