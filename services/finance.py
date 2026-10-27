"""잔액·예비비·연습 가능 횟수·연말 예상 잔액 계산."""
from services.dues import member_dues_rows
from services.settings import get_settings


def _sum(conn, year: int, type_: str, where: str = "", params=()) -> int:
    row = conn.execute(
        f'SELECT COALESCE(SUM(amount), 0) FROM "transaction" '
        f"WHERE type = ? AND strftime('%Y', date) = ? {where}",
        (type_, str(year), *params),
    ).fetchone()
    return row[0]


def finance_summary(conn, year=None) -> dict:
    s = get_settings(conn, year)
    year = s["year"]
    income = _sum(conn, year, "수입")
    expense = _sum(conn, year, "지출")
    balance = s["carry_over"] + income - expense

    league_paid = _sum(conn, year, "지출", "AND category = ?", ("리그비",))
    remaining_league = max(0, s["league_fee"] - league_paid)

    dues_rows = member_dues_rows(conn, year)
    dues_total = sum(r["due"] for r in dues_rows)
    # 휴면 전환 전에 낸 금액 등 부과액을 넘는 납부분도 수입으로 인정한다.
    dues_expected = sum(max(r["due"], r["paid"]) for r in dues_rows)
    dues_income = _sum(conn, year, "수입", "AND category = ?", ("회비",))
    other_income = income - dues_income

    scheduled_fee = conn.execute(
        "SELECT COALESCE(SUM(venue_fee), 0) FROM schedule "
        "WHERE kind = '연습' AND status = '예정' AND strftime('%Y', date) = ?",
        (str(year),),
    ).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(*) FROM schedule WHERE kind = '연습' AND status = '완료' AND strftime('%Y', date) = ?",
        (str(year),),
    ).fetchone()[0]

    # 연간 계획 기준 (PRD 3장): 이월 + 부과 회비 - 리그비 - 예비비
    total_resources = s["carry_over"] + dues_total
    practice_budget = total_resources - s["league_fee"] - s["reserve"]
    fee = s["venue_fee"]
    max_practices = max(0, practice_budget // fee) if fee else 0

    projected_year_end = (
        s["carry_over"] + other_income + dues_expected
        - (expense + remaining_league + scheduled_fee)
    )
    additional = max(0, (projected_year_end - s["reserve"]) // fee) if fee else 0

    return {
        "year": year,
        "carry_over": s["carry_over"],
        "income": income,
        "expense": expense,
        "balance": balance,
        "reserve": s["reserve"],
        "usable_balance": balance - s["reserve"],
        "remaining_league": remaining_league,
        # PRD 3장 대시보드 식: 잔액 - 예비비 - 잔여 리그비 (아직 못 걷은 회비는 반영되지 않음)
        "practice_available_now": balance - s["reserve"] - remaining_league,
        "total_resources": total_resources,
        "practice_budget": practice_budget,
        "max_practices": max_practices,
        "practices_done": done,
        "scheduled_practice_fee": scheduled_fee,
        "additional_practices_possible": additional,
        "projected_year_end": projected_year_end,
    }
