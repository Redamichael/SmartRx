"""
SmartRx AI — Lightweight DB helper
Works with sqlite3 (demo) and can be swapped for SQLAlchemy on PostgreSQL.
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(r"C:\Users\RedaM\SmartRx\smartrx_demo.db")


def _row_factory(cursor, row):
    """Return rows as dicts."""
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = _row_factory
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params: tuple = (), one: bool = False):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()


def execute(sql: str, params: tuple = ()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def executemany(sql: str, params_list: list):
    with get_db() as conn:
        conn.executemany(sql, params_list)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km."""
    import math
    R = 6371
    rl = math.radians
    d_lat = rl(lat2 - lat1)
    d_lon = rl(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(rl(lat1)) * math.cos(rl(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
