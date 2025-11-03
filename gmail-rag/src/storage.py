import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

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
