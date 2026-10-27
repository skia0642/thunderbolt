"""일정 등록·수정과 연습 대관료 지출 연동."""
import re
from datetime import date

from services.errors import ValidationError
from services.finance import finance_summary
from services.settings import as_of, get_settings

KINDS = ("경기", "연습")
STATUSES = ("예정", "완료", "취소")
RESULTS = ("승", "패", "무")
MAX_FEE = 100_000_000


def remaining_schedule(conn, year=None) -> list[dict]:
    """기준일 이후(당일 포함) 예정 일정."""
    s = get_settings(conn, year)
    today = as_of(conn, s["year"]).isoformat()
    rows = conn.execute(
        "SELECT * FROM schedule WHERE date >= ? AND status = '예정' AND strftime('%Y', date) = ? ORDER BY date, time",
        (today, str(s["year"])),
    ).fetchall()
    return [dict(r) for r in rows]


def remaining_counts(conn, year=None) -> dict:
    rows = remaining_schedule(conn, year)
    return {
        "경기": sum(1 for r in rows if r["kind"] == "경기"),
        "연습": sum(1 for r in rows if r["kind"] == "연습"),
    }


def _clean(conn, data: dict) -> dict:
    s = get_settings(conn)
    errors = []
    raw = data.get("date")
    d = None
    try:
        d = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        if d.year != s["year"]:
            errors.append(f"일정 날짜는 {s['year']}년 안이어야 합니다.")
    except ValueError:
        errors.append("날짜 형식이 올바르지 않습니다.")

    t = str(data.get("time") or "").strip() or None
    if t and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        errors.append("시간은 HH:MM 형식으로 입력하세요.")

    kind = data.get("kind")
    if kind not in KINDS:
        errors.append("구분은 경기 또는 연습이어야 합니다.")
    status = data.get("status") or "예정"
    if status not in STATUSES:
        errors.append("상태는 예정/완료/취소 중 하나여야 합니다.")

    place = str(data.get("place") or "").strip() or None
    opponent = str(data.get("opponent") or "").strip() or None
    if place and len(place) > 50:
        errors.append("장소는 50자 이하로 입력하세요.")
    if opponent and len(opponent) > 30:
        errors.append("상대팀은 30자 이하로 입력하세요.")

    fee = data.get("venue_fee")
    if kind == "연습":
        fee = s["venue_fee"] if fee in (None, "") else fee
        try:
            fee = int(fee)
            if not 0 <= fee <= MAX_FEE:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("대관료는 0원 이상의 정수여야 합니다.")
            fee = 0
    else:
        fee = 0

    result = data.get("result") or None
    if result is not None and (kind != "경기" or result not in RESULTS):
        errors.append("경기 결과는 경기 일정에만 승/패/무로 입력할 수 있습니다.")
    if errors:
        raise ValidationError(errors)
    return {"date": d.isoformat(), "time": t, "kind": kind, "place": place,
            "opponent": opponent if kind == "경기" else None, "venue_fee": fee,
            "status": status, "result": result}


def sync_venue_transaction(conn, schedule_id: int) -> None:
    """완료된 연습은 대관료 지출 1건을 갖고, 그 외 상태에서는 지출이 없다."""
    sc = conn.execute("SELECT * FROM schedule WHERE id = ?", (schedule_id,)).fetchone()
    tx = conn.execute(
        'SELECT id FROM "transaction" WHERE schedule_id = ? AND category = \'대관료\'', (schedule_id,)
    ).fetchone()
    wanted = sc is not None and sc["kind"] == "연습" and sc["status"] == "완료" and sc["venue_fee"] > 0
    if wanted:
        memo = f"연습 대관료 ({sc['date']})"
        if tx:
            conn.execute('UPDATE "transaction" SET date = ?, amount = ?, memo = ? WHERE id = ?',
                         (sc["date"], sc["venue_fee"], memo, tx["id"]))
        else:
            conn.execute(
                'INSERT INTO "transaction" (date, type, category, amount, memo, schedule_id) '
                "VALUES (?, '지출', '대관료', ?, ?, ?)", (sc["date"], sc["venue_fee"], memo, schedule_id),
            )
    elif tx:
        conn.execute('DELETE FROM "transaction" WHERE id = ?', (tx["id"],))


def budget_warning(conn) -> str | None:
    """연말 예상 잔액이 예비비 아래이면 경고 문구를 돌려준다. 등록은 막지 않는다."""
    f = finance_summary(conn)
    if f["projected_year_end"] < f["reserve"]:
        short = f["reserve"] - f["projected_year_end"]
        return (f"연말 예상 잔액이 {f['projected_year_end']:,}원으로 예비비 {f['reserve']:,}원보다 "
                f"{short:,}원 부족합니다. (등록은 되었습니다)")
    return None


def create_schedule(conn, data: dict) -> tuple[int, str | None]:
    c = _clean(conn, data)
    cur = conn.execute(
        "INSERT INTO schedule (date, time, kind, place, opponent, venue_fee, status, result) "
        "VALUES (:date, :time, :kind, :place, :opponent, :venue_fee, :status, :result)", c,
    )
    sync_venue_transaction(conn, cur.lastrowid)
    conn.commit()
    return cur.lastrowid, budget_warning(conn) if c["kind"] == "연습" else None


def update_schedule(conn, schedule_id: int, data: dict) -> str | None:
    if conn.execute("SELECT 1 FROM schedule WHERE id = ?", (schedule_id,)).fetchone() is None:
        raise ValidationError("존재하지 않는 일정입니다.")
    c = _clean(conn, data)
    conn.execute(
        "UPDATE schedule SET date=:date, time=:time, kind=:kind, place=:place, opponent=:opponent, "
        "venue_fee=:venue_fee, status=:status, result=:result WHERE id=:id", {**c, "id": schedule_id},
    )
    sync_venue_transaction(conn, schedule_id)
    conn.commit()
    return budget_warning(conn) if c["kind"] == "연습" else None


def set_status(conn, schedule_id: int, status: str) -> str | None:
    row = conn.execute("SELECT * FROM schedule WHERE id = ?", (schedule_id,)).fetchone()
    if row is None:
        raise ValidationError("존재하지 않는 일정입니다.")
    data = dict(row)
    data["status"] = status
    return update_schedule(conn, schedule_id, data)


def delete_schedule(conn, schedule_id: int) -> None:
    conn.execute('DELETE FROM "transaction" WHERE schedule_id = ?', (schedule_id,))
    conn.execute("DELETE FROM schedule WHERE id = ?", (schedule_id,))
    conn.commit()
