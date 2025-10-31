import sqlite3
from pathlib import Path
import json

DB_PATH = Path(__file__).parent / "reports.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              kind TEXT NOT NULL,         -- daily | weekly | monthly
              mode TEXT NOT NULL,         -- data | analysis
              date TEXT NOT NULL,         -- YYYY-MM-DD
              title TEXT NOT NULL,
              markdown TEXT NOT NULL,
              sources TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )

def save_report(kind: str, mode: str, date: str, title: str, markdown: str, sources: list, created_at: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO reports(kind, mode, date, title, markdown, sources, created_at) VALUES(?,?,?,?,?,?,?)",
            (kind, mode, date, title, markdown, json.dumps(sources), created_at)
        )
        return cur.lastrowid

def list_reports(kind: str | None = None, mode: str | None = None) -> list[dict]:
    q = "SELECT id, kind, mode, date, title, markdown, sources, created_at FROM reports"
    params = []
    where = []
    if kind:
        where.append("kind=?"); params.append(kind)
    if mode:
        where.append("mode=?"); params.append(mode)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY date DESC, id DESC"
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "kind": r["kind"],
                "mode": r["mode"],
                "date": r["date"],
                "title": r["title"],
                "markdown": r["markdown"],
                "sources": json.loads(r["sources"]),
                "created_at": r["created_at"],
            })
        return out

init_db()
