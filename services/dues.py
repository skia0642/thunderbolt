"""회비 부과·납부 현황 계산. 휴면 회원은 부과액 0원이다 (PRD F-2-3a)."""
import calendar
from datetime import date

from services.settings import as_of as get_as_of
from services.settings import get_settings

DUE_MONTHS = (1, 4, 7, 11)
INSTALLMENTS = 4


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def member_dues_rows(conn, year=None) -> list[dict]:
    """회원별 부과액·납부액·납부율·상태. 활동/휴면 모두 포함한다."""
    s = get_settings(conn, year)
    year = s["year"]
    today = get_as_of(conn, year)
    rows = conn.execute(
        """
        SELECT m.id AS member_id, m.name, m.status, m.pay_type,
               d.id AS dues_id, d.amount_due, d.installments
        FROM member m LEFT JOIN dues d ON d.member_id = m.id AND d.year = ?
        ORDER BY m.id
        """,
        (year,),
    ).fetchall()
    payments: dict[int, dict[int, int]] = {}
    for p in conn.execute(
        "SELECT p.member_id, p.round, p.amount FROM payment p JOIN dues d ON d.id = p.dues_id WHERE d.year = ?",
        (year,),
    ):
        payments.setdefault(p["member_id"], {})[p["round"]] = p["amount"]

    result = []
    for r in rows:
        paid_rounds = payments.get(r["member_id"], {})
        paid = sum(paid_rounds.values())
        dormant = r["status"] == "휴면"
        base = r["amount_due"] if r["amount_due"] is not None else s["annual_dues"]
        n = r["installments"] or (INSTALLMENTS if r["pay_type"] == "분납" else 1)
        due = 0 if dormant else base

        if n == INSTALLMENTS:
            per_round = base // INSTALLMENTS
            rounds_due = [i + 1 for i, m in enumerate(DUE_MONTHS) if m <= today.month]
            due_to_date = 0 if dormant else per_round * len(rounds_due)
            # 아직 도래하지 않은 회차를 미리 낸 금액은 앞 회차의 미납을 가리지 않도록 제외한다.
            paid_to_date = sum(paid_rounds.get(rd, 0) for rd in rounds_due)
            overdue = [] if dormant else [
                i + 1 for i, m in enumerate(DUE_MONTHS)
                if month_end(year, m) < today and (i + 1) not in paid_rounds
            ]
        else:
            due_to_date = due
            paid_to_date = min(paid, due)
            overdue = []

        if dormant:
            status = "면제"
        elif paid >= due:
            status = "완납"
        elif overdue:
            status = "연체"
        elif n == INSTALLMENTS and paid > 0:
            status = "분납중"
        else:
            status = "미납"

        result.append({
            "member_id": r["member_id"], "name": r["name"], "status": r["status"],
            "pay_type": r["pay_type"], "installments": n,
            "due": due, "paid": paid, "unpaid": max(0, due - paid),
            "due_to_date": due_to_date, "paid_to_date": paid_to_date,
            "rate": round(paid / due * 100, 1) if due else None,
            "rate_to_date": round(paid_to_date / due_to_date * 100, 1) if due_to_date else None,
            "pay_status": status, "paid_rounds": sorted(paid_rounds), "overdue_rounds": overdue,
        })
    return result


def overall_payment_rate(conn, year=None) -> float | None:
    """활동 회원 기준 연간 납부율(%). 부과 대상이 없으면 None."""
    rows = [r for r in member_dues_rows(conn, year) if r["status"] == "활동"]
    due = sum(r["due"] for r in rows)
    if not due:
        return None
    return round(sum(min(r["paid"], r["due"]) for r in rows) / due * 100, 1)
