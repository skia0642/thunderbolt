from datetime import date

from services.errors import ValidationError


def get_settings(conn, year=None) -> dict:
    if year is None:
        row = conn.execute("SELECT * FROM settings ORDER BY year DESC LIMIT 1").fetchone()
    else:
        row = conn.execute("SELECT * FROM settings WHERE year = ?", (year,)).fetchone()
    if row is None:
        raise LookupError("설정이 없습니다. 샘플 데이터를 생성하거나 설정을 입력하세요.")
    return dict(row)


def as_of(conn, year=None) -> date:
    """프로그램이 '오늘'로 취급하는 기준일."""
    return date.fromisoformat(get_settings(conn, year)["as_of"])


def list_years(conn) -> list[int]:
    """설정이 있는 연도, 최신순."""
    return [r[0] for r in conn.execute("SELECT year FROM settings ORDER BY year DESC")]


def set_as_of_today(conn, today: date | None = None) -> str:
    """기준일을 오늘 날짜로 맞춘다. 현재(최신) 연도 안일 때만 가능하다."""
    today = today or date.today()
    s = get_settings(conn)
    if today.year != s["year"]:
        raise ValidationError(f"오늘({today.isoformat()})은 {s['year']}년 설정 범위 밖입니다. 새 연도를 먼저 만들거나 날짜를 직접 선택하세요.")
    conn.execute("UPDATE settings SET as_of = ? WHERE year = ?", (today.isoformat(), s["year"]))
    conn.commit()
    return today.isoformat()


AMOUNT_FIELDS = {
    "carry_over": "이월 잔액", "reserve": "차년도 예비비", "league_fee": "리그비",
    "annual_dues": "연 회비", "venue_fee": "연습 대관료",
}
MAX_AMOUNT = 1_000_000_000


def _clean_settings(data: dict, year: int) -> dict:
    errors, out = [], {}
    for key, label in AMOUNT_FIELDS.items():
        try:
            v = int(data.get(key))
            if not 0 <= v <= MAX_AMOUNT:
                raise ValueError
            out[key] = v
        except (TypeError, ValueError):
            errors.append(f"{label}은(는) 0원 이상의 정수여야 합니다.")
    try:
        g = int(data.get("league_games"))
        if not 0 <= g <= 100:
            raise ValueError
        out["league_games"] = g
    except (TypeError, ValueError):
        errors.append("리그 경기 수는 0~100 사이의 정수여야 합니다.")
    try:
        raw = data.get("as_of")
        d = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        if d.year != year:
            errors.append(f"기준일은 {year}년 안의 날짜여야 합니다.")
        out["as_of"] = d.isoformat()
    except ValueError:
        errors.append("기준일 형식이 올바르지 않습니다.")
    if errors:
        raise ValidationError(errors)
    return out


def update_settings(conn, year: int, data: dict) -> None:
    if conn.execute("SELECT 1 FROM settings WHERE year = ?", (year,)).fetchone() is None:
        raise ValidationError("존재하지 않는 연도입니다.")
    c = _clean_settings(data, year)
    conn.execute(
        "UPDATE settings SET carry_over=:carry_over, reserve=:reserve, league_fee=:league_fee, "
        "annual_dues=:annual_dues, venue_fee=:venue_fee, league_games=:league_games, as_of=:as_of WHERE year=:year",
        {**c, "year": year},
    )
    conn.commit()


def create_year(conn, year: int, data: dict) -> None:
    """새 연도 설정을 만든다. 이월 잔액은 data로 받은 값(회장단이 확정한 금액)을 쓴다."""
    latest = get_settings(conn)["year"]
    if year <= latest:
        raise ValidationError(f"{latest}년 이후의 연도만 만들 수 있습니다.")
    data = {**data, "as_of": date(year, 1, 1)}  # 기준일은 새 연도 1월 1일에서 시작한다
    c = _clean_settings(data, year)
    conn.execute(
        "INSERT INTO settings (year, carry_over, reserve, league_fee, annual_dues, venue_fee, league_games, as_of) "
        "VALUES (:year, :carry_over, :reserve, :league_fee, :annual_dues, :venue_fee, :league_games, :as_of)",
        {**c, "year": year},
    )
    conn.commit()
