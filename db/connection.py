import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from db.schema import SCHEMA, TABLES

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "club.db"


def db_path() -> Path:
    return Path(os.environ.get("CLUB_DB", DEFAULT_DB))


def get_conn(path=None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    """모든 테이블을 비우고 스키마를 다시 만든다."""
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in TABLES:
        conn.execute(f'DROP TABLE IF EXISTS "{t}"')
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)


def ensure_db() -> sqlite3.Connection:
    """DB가 없거나 비어 있으면 스키마를 만들고 가상 데이터를 채운다."""
    conn = get_conn()
    init_schema(conn)
    has_settings = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    if not has_settings:
        from seed.seed_data import seed
        seed(conn)
    return conn


@contextmanager
def connect():
    """with 블록이 끝나면(예외·st.rerun 포함) 연결을 닫는다."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
