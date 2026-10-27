"""수입·지출 내역. 납부·대관료와 연동된 거래는 원천 화면에서만 바꾼다."""
from datetime import date

from services.errors import ValidationError
from services.settings import get_settings

INCOME_CATEGORIES = ("회비", "기타")
EXPENSE_CATEGORIES = ("리그비", "대관료", "장비", "기타")
MAX_AMOUNT = 1_000_000_000


def linked_kind(conn, transaction_id: int) -> str | None:
    """연동된 원천('납부'/'일정')을 돌려준다. 수동 입력이면 None."""
    if conn.execute("SELECT 1 FROM payment WHERE transaction_id = ?", (transaction_id,)).fetchone():
        return "납부"
    row = conn.execute('SELECT schedule_id FROM "transaction" WHERE id = ?', (transaction_id,)).fetchone()
    if row and row["schedule_id"]:
        return "일정"
    return None


def _clean(conn, data: dict) -> dict:
    s = get_settings(conn)
    errors = []
    try:
        raw = data.get("date")
        d = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        if d.year != s["year"]:
            errors.append(f"날짜는 {s['year']}년 안이어야 합니다.")
    except ValueError:
        errors.append("날짜 형식이 올바르지 않습니다.")
        d = None
    type_ = data.get("type")
    if type_ not in ("수입", "지출"):
        errors.append("구분은 수입 또는 지출이어야 합니다.")
    category = str(data.get("category") or "").strip()
    allowed = INCOME_CATEGORIES if type_ == "수입" else EXPENSE_CATEGORIES
    if type_ in ("수입", "지출") and category not in allowed:
        errors.append(f"분류는 {', '.join(allowed)} 중 하나여야 합니다.")
    try:
        amount = int(data.get("amount"))
        if not 0 < amount <= MAX_AMOUNT:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("금액은 1원 이상의 정수여야 합니다.")
        amount = 0
    memo = str(data.get("memo") or "").strip() or None
    if memo and len(memo) > 100:
        errors.append("메모는 100자 이하로 입력하세요.")
    if errors:
        raise ValidationError(errors)
    return {"date": d.isoformat(), "type": type_, "category": category, "amount": amount, "memo": memo}


def add_transaction(conn, data: dict) -> int:
    """수동 거래 등록. 회비 수입은 회원 납부 기록(payments.pay)으로만 만든다."""
    if data.get("type") == "수입" and data.get("category") == "회비":
        raise ValidationError("회비 수입은 회원 납부 기록으로 등록하세요.")
    c = _clean(conn, data)
    cur = conn.execute(
        'INSERT INTO "transaction" (date, type, category, amount, memo) VALUES (:date, :type, :category, :amount, :memo)', c
    )
    conn.commit()
    return cur.lastrowid


def _require_manual(conn, transaction_id: int) -> None:
    if conn.execute('SELECT 1 FROM "transaction" WHERE id = ?', (transaction_id,)).fetchone() is None:
        raise ValidationError("존재하지 않는 거래입니다.")
    kind = linked_kind(conn, transaction_id)
    if kind == "납부":
        raise ValidationError("회원 납부와 연동된 거래입니다. 회원 화면에서 납부를 취소하세요.")
    if kind == "일정":
        raise ValidationError("일정과 연동된 거래입니다. 일정 화면에서 수정하세요.")


def update_transaction(conn, transaction_id: int, data: dict) -> None:
    _require_manual(conn, transaction_id)
    if data.get("type") == "수입" and data.get("category") == "회비":
        raise ValidationError("회비 수입은 회원 납부 기록으로 등록하세요.")
    c = _clean(conn, data)
    conn.execute(
        'UPDATE "transaction" SET date=:date, type=:type, category=:category, amount=:amount, memo=:memo WHERE id=:id',
        {**c, "id": transaction_id},
    )
    conn.commit()


def delete_transaction(conn, transaction_id: int) -> None:
    _require_manual(conn, transaction_id)
    conn.execute('DELETE FROM "transaction" WHERE id = ?', (transaction_id,))
    conn.commit()


def list_transactions(conn, start=None, end=None, type_=None, category=None, year=None) -> list[dict]:
    year = get_settings(conn, year)["year"]
    q = ("SELECT t.*, CASE WHEN p.id IS NOT NULL THEN '납부' WHEN t.schedule_id IS NOT NULL THEN '일정' "
         "ELSE '수동' END AS source FROM \"transaction\" t LEFT JOIN payment p ON p.transaction_id = t.id "
         "WHERE strftime('%Y', t.date) = ?")
    params: list = [str(year)]
    if start:
        q += " AND t.date >= ?"
        params.append(str(start))
    if end:
        q += " AND t.date <= ?"
        params.append(str(end))
    if type_:
        q += " AND t.type = ?"
        params.append(type_)
    if category:
        q += " AND t.category = ?"
        params.append(category)
    q += " ORDER BY t.date DESC, t.id DESC"
    return [dict(r) for r in conn.execute(q, params)]


def monthly_summary(conn, year=None) -> list[dict]:
    """1~12월 수입·지출 합계."""
    year = get_settings(conn, year)["year"]
    sums = {(r["m"], r["type"]): r["total"] for r in conn.execute(
        "SELECT CAST(strftime('%m', date) AS INTEGER) AS m, type, SUM(amount) AS total "
        "FROM \"transaction\" WHERE strftime('%Y', date) = ? GROUP BY m, type", (str(year),))}
    return [{"월": f"{m}월", "수입": sums.get((m, "수입"), 0), "지출": sums.get((m, "지출"), 0)} for m in range(1, 13)]
