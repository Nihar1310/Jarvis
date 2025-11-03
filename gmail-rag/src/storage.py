import json
import os
from typing import Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .utils import normalize_material_name

DB_URL = os.getenv("DB_URL","sqlite:///./data/price_memory.db")

def db() -> Engine:
    return create_engine(DB_URL, future=True)

def init_schema():
    eng = db()
    with eng.begin() as cx:
        cx.exec_driver_sql(open("src/models.sql").read())

def row(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).fetchone()

def rows(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).fetchall()


def load_material_alias_index(conn=None) -> Dict[str, Dict[str, str]]:
    own_conn = False
    if conn is None:
        conn = db().connect()
        own_conn = True

    index: Dict[str, Dict[str, str]] = {}
    result = conn.execute(text("SELECT id, name, aliases FROM materials")).fetchall()

    for row in result:
        names = [row.name]
        if row.aliases:
            try:
                alias_values = json.loads(row.aliases)
                if isinstance(alias_values, list):
                    names.extend([alias for alias in alias_values if isinstance(alias, str)])
            except json.JSONDecodeError:
                pass

        for alias in names:
            normalized = normalize_material_name(alias)
            if not normalized:
                continue
            index[normalized] = {"id": row.id, "name": row.name}

    if own_conn:
        conn.close()

    return index
