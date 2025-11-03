CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE,
  email_domain TEXT,
  region TEXT,
  tier TEXT
);

CREATE TABLE IF NOT EXISTS materials(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE,
  grade TEXT,
  aliases TEXT -- JSON string '["alias1","alias2"]'
);

CREATE TABLE IF NOT EXISTS emails(
  gmail_id TEXT PRIMARY KEY,
  subject TEXT,
  from_addr TEXT,
  to_addrs TEXT,
  date_ts TEXT,
  doc_type TEXT,        -- QUOTATION, PO, INVOICE, STOCK_SHEET, RATE_CIRCULAR, PAYMENT, OTHER
  direction TEXT,       -- INCOMING/OUTGOING
  display_url TEXT,
  has_attachment INTEGER,
  body TEXT
);

CREATE TABLE IF NOT EXISTS quotes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gmail_id TEXT REFERENCES emails(gmail_id),
  customer_id INTEGER,
  material_id INTEGER,
  qty REAL,
  unit TEXT,
  rate REAL,
  basis TEXT,
  freight TEXT,
  discount_pct REAL,
  cd_pct REAL,
  date_ts TEXT,
  parsed_confidence REAL,
  source_note TEXT
);

CREATE TABLE IF NOT EXISTS supplier_rates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier TEXT,
  material_id INTEGER,
  base_rate REAL,
  stockist_discount_pct REAL,
  cash_discount_pct REAL,
  freight REAL,
  effective_date TEXT,
  source_gmail_id TEXT
);

CREATE TABLE IF NOT EXISTS purchase_orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gmail_id TEXT,
  po_no TEXT,
  customer_id INTEGER,
  vendor TEXT,
  buyer TEXT,
  ship_to TEXT,
  date_ts TEXT,
  raw_text TEXT
);

CREATE TABLE IF NOT EXISTS po_lines(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_order_id INTEGER,
  description TEXT,
  quantity TEXT,
  unit_price TEXT,
  amount TEXT,
  material_id INTEGER
);
