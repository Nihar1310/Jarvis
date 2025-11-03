from __future__ import annotations

import os, base64, pickle, pathlib, json
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from sqlalchemy import text
from datetime import datetime

from .storage import db
from .utils import classify_doc_type

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def gmail_service():
    token_dir = os.getenv("GMAIL_TOKEN_DIR","./data/tokens")
    pathlib.Path(token_dir).mkdir(parents=True, exist_ok=True)
    token_path = f"{token_dir}/token.pickle"
    creds = None
    if os.path.exists(token_path):
        with open(token_path,"rb") as f: creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config({
              "installed":{
                "client_id":os.getenv("GMAIL_OAUTH_CLIENT_ID"),
                "client_secret":os.getenv("GMAIL_OAUTH_CLIENT_SECRET"),
                "redirect_uris":["urn:ietf:wg:oauth:2.0:oob","http://localhost"],
                "auth_uri":"https://accounts.google.com/o/oauth2/auth",
                "token_uri":"https://oauth2.googleapis.com/token"}
            }, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path,"wb") as f: pickle.dump(creds,f)
    return build("gmail","v1",credentials=creds)

BUSINESS_Q = "(quotation OR quote OR offer OR PO OR invoice OR dispatch OR stock OR rate OR approval OR payment OR overdue)"
RECENT_Q = "newer_than:2d"

def list_message_ids(svc, max_results=200)->List[str]:
    q = f"({BUSINESS_Q}) {RECENT_Q}"
    res = svc.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    return [m["id"] for m in res.get("messages", [])]

def get_msg(svc, mid): return svc.users().messages().get(userId="me", id=mid, format="full").execute()

def _header(msg, name):
    for h in msg.get("payload",{}).get("headers",[]):
        if h["name"].lower()==name: return h["value"]
    return ""

def decode(body):
    data = body.get("data")
    return base64.urlsafe_b64decode(data).decode(errors="ignore") if data else ""

def extract_text_and_attachments(msg):
    text, atts = "", []
    payload = msg.get("payload",{})
    parts = payload.get("parts") or [payload]
    for p in parts:
        mime = p.get("mimeType")
        body = p.get("body",{})
        if mime in ("text/plain","text/html"):
            text += "\n" + decode(body)
        if p.get("filename"):
            att_id = body.get("attachmentId")
            if att_id:
                atts.append({"attachmentId": att_id, "filename": p["filename"], "mimeType": mime})
    return text, atts

def download_attachment(svc, msg_id, att_id, filename, outdir="./data/attachments"):
    pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
    att = svc.users().messages().attachments().get(userId="me", messageId=msg_id, id=att_id).execute()
    data = base64.urlsafe_b64decode(att["data"])
    path = os.path.join(outdir, f"{msg_id}__{filename}")
    with open(path,"wb") as f: f.write(data)
    return path

def sync_recent():
    svc = gmail_service()
    mids = list_message_ids(svc)
    eng = db()
    report = {"emails":0, "attachments":0}
    with eng.begin() as cx:
        for mid in mids:
            msg = get_msg(svc, mid)
            subj = _header(msg,"subject"); frm = _header(msg,"from"); date_raw = _header(msg,"date")
            to = _header(msg,"to")
            text, atts = extract_text_and_attachments(msg)
            doctype = classify_doc_type(subj, text)
            has_att = 1 if atts else 0
            display_url = f"https://mail.google.com/mail/#all/{mid}"
            cx.exec_driver_sql(text("""
              INSERT OR IGNORE INTO emails(gmail_id,subject,from_addr,to_addrs,date_ts,doc_type,direction,display_url,has_attachment,body)
              VALUES(:gid,:subj,:frm,:to,:date,:dt,:dir,:url,:ha,:body)
            """), dict(gid=mid, subj=subj, frm=frm, to=to, date=date_raw, dt=doctype,
                       dir=("OUTGOING" if "anujtraders" in frm.lower() else "INCOMING"),
                       url=display_url, ha=has_att, body=text))
            report["emails"] += 1
            for a in atts:
                path = download_attachment(svc, mid, a["attachmentId"], a["filename"])
                report["attachments"] += 1
    return report
