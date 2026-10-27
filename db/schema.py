"""SQLite 스키마. 금액은 모두 정수(원)로 저장한다."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    year         INTEGER PRIMARY KEY,
    carry_over   INTEGER NOT NULL,
    reserve      INTEGER NOT NULL,
    league_fee   INTEGER NOT NULL,
    annual_dues  INTEGER NOT NULL,
    venue_fee    INTEGER NOT NULL,
    league_games INTEGER NOT NULL,
    as_of        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS member (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL,
    position    TEXT,
    back_number INTEGER,
    joined_at   TEXT,
    status      TEXT NOT NULL DEFAULT '활동' CHECK (status IN ('활동', '휴면')),
    pay_type    TEXT NOT NULL DEFAULT '일괄' CHECK (pay_type IN ('일괄', '분납')),
    UNIQUE (name, phone)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_member_back_number ON member(back_number) WHERE back_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS dues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id    INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    year         INTEGER NOT NULL,
    amount_due   INTEGER NOT NULL,
    installments INTEGER NOT NULL CHECK (installments IN (1, 4)),
    due_months   TEXT NOT NULL DEFAULT '',
    UNIQUE (member_id, year)
);

CREATE TABLE IF NOT EXISTS schedule (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT NOT NULL,
    time      TEXT,
    kind      TEXT NOT NULL CHECK (kind IN ('경기', '연습')),
    place     TEXT,
    opponent  TEXT,
    venue_fee INTEGER NOT NULL DEFAULT 0,
    status    TEXT NOT NULL DEFAULT '예정' CHECK (status IN ('예정', '완료', '취소')),
    result    TEXT
);

CREATE TABLE IF NOT EXISTS "transaction" (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('수입', '지출')),
    category    TEXT NOT NULL,
    amount      INTEGER NOT NULL CHECK (amount >= 0),
    memo        TEXT,
    schedule_id INTEGER REFERENCES schedule(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS payment (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id      INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    dues_id        INTEGER NOT NULL REFERENCES dues(id) ON DELETE CASCADE,
    round          INTEGER NOT NULL,
    amount         INTEGER NOT NULL CHECK (amount > 0),
    paid_at        TEXT NOT NULL,
    transaction_id INTEGER REFERENCES "transaction"(id) ON DELETE SET NULL,
    UNIQUE (dues_id, round)
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES schedule(id) ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    attended    INTEGER NOT NULL CHECK (attended IN (0, 1)),
    UNIQUE (schedule_id, member_id)
);
"""

TABLES = ["attendance", "payment", "transaction", "schedule", "dues", "member", "settings"]
