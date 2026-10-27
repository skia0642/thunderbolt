"""참석율 = 참석 횟수 ÷ 종료(완료)된 일정 수 × 100."""
from services.errors import ValidationError
from services.settings import get_settings


def completed_counts(conn, year: int) -> dict:
    rows = conn.execute(
        "SELECT kind, COUNT(*) FROM schedule WHERE status = '완료' AND strftime('%Y', date) = ? GROUP BY kind",
        (str(year),),
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    counts["전체"] = sum(counts.values())
    return counts


def member_attendance_rows(conn, year=None) -> list[dict]:
    year = get_settings(conn, year)["year"]
    totals = completed_counts(conn, year)
    attended: dict[int, dict[str, int]] = {}
    for r in conn.execute(
        """
        SELECT a.member_id, s.kind, COUNT(*) AS n
        FROM attendance a JOIN schedule s ON s.id = a.schedule_id
        WHERE a.attended = 1 AND s.status = '완료' AND strftime('%Y', s.date) = ?
        GROUP BY a.member_id, s.kind
        """,
        (str(year),),
    ):
        attended.setdefault(r["member_id"], {})[r["kind"]] = r["n"]

    def rate(n, total):
        return round(n / total * 100, 1) if total else None

    out = []
    for m in conn.execute("SELECT id, name, status FROM member ORDER BY id"):
        a = attended.get(m["id"], {})
        all_n = sum(a.values())
        out.append({
            "member_id": m["id"], "name": m["name"], "status": m["status"],
            "attended": all_n,
            "rate": rate(all_n, totals["전체"]),
            "game_rate": rate(a.get("경기", 0), totals.get("경기", 0)),
            "practice_rate": rate(a.get("연습", 0), totals.get("연습", 0)),
        })
    return out


def average_attendance_rate(conn, year=None) -> float | None:
    """활동 회원 평균 참석율(%)."""
    rates = [r["rate"] for r in member_attendance_rows(conn, year)
             if r["status"] == "활동" and r["rate"] is not None]
    return round(sum(rates) / len(rates), 1) if rates else None


def get_attendance(conn, schedule_id: int) -> dict[int, bool]:
    return {r["member_id"]: bool(r["attended"]) for r in
            conn.execute("SELECT member_id, attended FROM attendance WHERE schedule_id = ?", (schedule_id,))}


def save_attendance(conn, schedule_id: int, marks: dict[int, bool]) -> None:
    """완료된 일정의 출석을 저장한다. marks = {member_id: 참석 여부}."""
    row = conn.execute("SELECT status FROM schedule WHERE id = ?", (schedule_id,)).fetchone()
    if row is None:
        raise ValidationError("존재하지 않는 일정입니다.")
    if row["status"] != "완료":
        raise ValidationError("완료된 일정에만 출석을 기록할 수 있습니다.")
    for member_id, attended in marks.items():
        conn.execute(
            "INSERT INTO attendance (schedule_id, member_id, attended) VALUES (?, ?, ?) "
            "ON CONFLICT(schedule_id, member_id) DO UPDATE SET attended = excluded.attended",
            (schedule_id, member_id, 1 if attended else 0),
        )
    conn.commit()


def attendance_history(conn, member_id: int, year=None) -> list[dict]:
    year = get_settings(conn, year)["year"]
    rows = conn.execute(
        "SELECT s.date, s.kind, s.opponent, s.place, COALESCE(a.attended, 0) AS attended "
        "FROM schedule s LEFT JOIN attendance a ON a.schedule_id = s.id AND a.member_id = ? "
        "WHERE s.status = '완료' AND strftime('%Y', s.date) = ? ORDER BY s.date DESC",
        (member_id, str(year)),
    )
    return [dict(r) for r in rows]
