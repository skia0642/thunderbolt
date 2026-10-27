"""회비 납부 기록. 납부(payment)와 수입 거래(transaction)는 항상 함께 생기고 함께 사라진다."""
from datetime import date

from services.dues import DUE_MONTHS, INSTALLMENTS, month_end
from services.errors import ValidationError
from services.settings import as_of, get_settings


def ensure_dues(conn, member_id: int, pay_type: str | None = None, year: int | None = None) -> int:
    """해당 연도 부과 행이 없으면 만들고 id를 돌려준다."""
    s = get_settings(conn, year)
    row = conn.execute("SELECT id FROM dues WHERE member_id = ? AND year = ?", (member_id, s["year"])).fetchone()
    if row:
        return row["id"]
    if pay_type is None:
        pay_type = conn.execute("SELECT pay_type FROM member WHERE id = ?", (member_id,)).fetchone()["pay_type"]
    n = INSTALLMENTS if pay_type == "분납" else 1
    cur = conn.execute(
        "INSERT INTO dues (member_id, year, amount_due, installments, due_months) VALUES (?, ?, ?, ?, ?)",
        (member_id, s["year"], s["annual_dues"], n, ",".join(map(str, DUE_MONTHS)) if n == INSTALLMENTS else ""),
    )
    return cur.lastrowid


def payment_schedule(conn, member_id: int, year: int | None = None) -> list[dict]:
    """회차별 납부 기한·금액·납부 여부."""
    s = get_settings(conn, year)
    today = as_of(conn, s["year"])
    member = conn.execute("SELECT name, status FROM member WHERE id = ?", (member_id,)).fetchone()
    if member is None:
        raise ValidationError("존재하지 않는 회원입니다.")
    dues_id = ensure_dues(conn, member_id, year=s["year"])
    d = conn.execute("SELECT * FROM dues WHERE id = ?", (dues_id,)).fetchone()
    paid = {p["round"]: p for p in conn.execute("SELECT * FROM payment WHERE dues_id = ?", (dues_id,))}
    rows = []
    if d["installments"] == INSTALLMENTS:
        for i, m in enumerate(DUE_MONTHS, start=1):
            rows.append({"round": i, "label": f"{i}회차 ({m}월)", "due_month": m, "amount": d["amount_due"] // INSTALLMENTS,
                         "deadline": month_end(s["year"], m)})
    else:
        rows.append({"round": 1, "label": "일시납", "due_month": 1, "amount": d["amount_due"],
                     "deadline": month_end(s["year"], 12)})
    for r in rows:
        p = paid.get(r["round"])
        r["paid"] = p is not None
        r["paid_at"] = p["paid_at"] if p else None
        r["paid_amount"] = p["amount"] if p else 0
        if p:
            r["state"] = "납부완료"
        elif d["installments"] == INSTALLMENTS and r["deadline"] < today:
            r["state"] = "연체"
        else:
            r["state"] = "미납"
    return rows


def _check_date(conn, raw, year: int) -> str:
    try:
        d = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    except ValueError:
        raise ValidationError("납부일 형식이 올바르지 않습니다.") from None
    if d.year != year:
        raise ValidationError(f"납부일은 {year}년 안의 날짜여야 합니다.")
    return d.isoformat()


def pay(conn, member_id: int, rnd: int, paid_at=None, year: int | None = None) -> int:
    """회차 납부를 기록하고 수입 거래를 함께 만든다. payment id를 돌려준다."""
    s = get_settings(conn, year)
    member = conn.execute("SELECT name, status FROM member WHERE id = ?", (member_id,)).fetchone()
    if member is None:
        raise ValidationError("존재하지 않는 회원입니다.")
    if member["status"] == "휴면":
        raise ValidationError("휴면 회원은 회비 부과 대상이 아닙니다. 활동으로 변경한 뒤 납부를 기록하세요.")
    dues_id = ensure_dues(conn, member_id, year=s["year"])
    d = conn.execute("SELECT * FROM dues WHERE id = ?", (dues_id,)).fetchone()
    if rnd < 1 or rnd > d["installments"]:
        raise ValidationError("올바른 회차가 아닙니다.")
    if conn.execute("SELECT 1 FROM payment WHERE dues_id = ? AND round = ?", (dues_id, rnd)).fetchone():
        raise ValidationError("이미 납부 처리된 회차입니다.")
    paid_at = _check_date(conn, paid_at or as_of(conn, s["year"]), s["year"])
    amount = d["amount_due"] // d["installments"]
    memo = f"{member['name']} 회비" + (f" ({rnd}회차)" if d["installments"] > 1 else "")
    tid = conn.execute(
        'INSERT INTO "transaction" (date, type, category, amount, memo) VALUES (?, \'수입\', \'회비\', ?, ?)',
        (paid_at, amount, memo),
    ).lastrowid
    pid = conn.execute(
        "INSERT INTO payment (member_id, dues_id, round, amount, paid_at, transaction_id) VALUES (?, ?, ?, ?, ?, ?)",
        (member_id, dues_id, rnd, amount, paid_at, tid),
    ).lastrowid
    conn.commit()
    return pid


def cancel_payment(conn, member_id: int, rnd: int, year: int | None = None) -> None:
    s = get_settings(conn, year)
    row = conn.execute(
        "SELECT p.id, p.transaction_id FROM payment p JOIN dues d ON d.id = p.dues_id "
        "WHERE p.member_id = ? AND p.round = ? AND d.year = ?", (member_id, rnd, s["year"]),
    ).fetchone()
    if row is None:
        raise ValidationError("납부 기록이 없는 회차입니다.")
    conn.execute("DELETE FROM payment WHERE id = ?", (row["id"],))
    if row["transaction_id"]:
        conn.execute('DELETE FROM "transaction" WHERE id = ?', (row["transaction_id"],))
    conn.commit()
