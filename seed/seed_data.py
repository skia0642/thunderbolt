"""가상 데이터 생성 (PRD 5.5장). 실행할 때마다 DB를 초기화하고 같은 데이터로 다시 만든다."""
import random

from db.connection import get_conn, reset_db

YEAR = 2026
AS_OF = "2026-10-27"

# 실존 인물과 무관한 임의의 이름
MEMBERS = [
    ("김도윤", "투수", 1), ("이서준", "포수", 2), ("박지후", "1루수", 3), ("최하준", "2루수", 4),
    ("정시우", "유격수", 6), ("강준서", "3루수", 5), ("조은우", "좌익수", 7), ("윤건우", "중견수", 8),
    ("장현우", "우익수", 9), ("임지호", "투수", 10), ("한승민", "포수", 22), ("오태윤", "1루수", 13),
    ("서재원", "2루수", 14), ("신민재", "유격수", 16), ("권성호", "3루수", 15), ("황동현", "좌익수", 17),
    ("안준혁", "중견수", 18), ("송우진", "우익수", 19), ("류시현", "투수", 21), ("문기태", "내야수", 24),
]
INSTALLMENT_MEMBERS = {3, 9, 14, 18}      # 분납 4명 (1-based id)
UNPAID_MEMBERS = {7, 16}                  # 일괄납부 중 미납 2명

GAME_DATES = [
    "2026-03-15", "2026-03-29", "2026-04-12", "2026-04-26", "2026-05-10", "2026-05-24",
    "2026-06-07", "2026-06-21", "2026-09-06", "2026-09-20", "2026-10-11", "2026-11-08",
]
PRACTICE_DATES = [
    "2026-03-01", "2026-04-05", "2026-05-03", "2026-06-14", "2026-09-13", "2026-10-18", "2026-11-01",
]
OPPONENTS = ["청룡", "독수리", "불곰", "파도", "태풍", "번개", "한울", "새벽", "거북이", "돌풍", "타이탄", "별빛"]
PLACES = ["한강 야구장", "잠실 보조구장", "양천 야구장", "송파 야구장"]
DUE_MONTHS = (1, 4, 7, 11)


def seed(conn=None) -> None:
    own = conn is None
    conn = conn or get_conn()
    reset_db(conn)
    rng = random.Random(2026)

    conn.execute(
        "INSERT INTO settings (year, carry_over, reserve, league_fee, annual_dues, venue_fee, league_games, as_of) "
        "VALUES (?, 2200000, 1000000, 3700000, 200000, 200000, 12, ?)",
        (YEAR, AS_OF),
    )

    # 회원 + 회비 부과
    for i, (name, pos, no) in enumerate(MEMBERS, start=1):
        pay_type = "분납" if i in INSTALLMENT_MEMBERS else "일괄"
        conn.execute(
            "INSERT INTO member (name, phone, position, back_number, joined_at, status, pay_type) "
            "VALUES (?, ?, ?, ?, ?, '활동', ?)",
            (name, f"010-0000-{i:04d}", pos, no, f"{2020 + i % 5}-0{1 + i % 9}-1{i % 9}", pay_type),
        )
        conn.execute(
            "INSERT INTO dues (member_id, year, amount_due, installments, due_months) VALUES (?, ?, 200000, ?, ?)",
            (i, YEAR, 4 if pay_type == "분납" else 1, "1,4,7,11" if pay_type == "분납" else ""),
        )

    # 일정
    sched_ids: dict[str, int] = {}
    for n, d in enumerate(GAME_DATES):
        status = "완료" if d < AS_OF else "예정"
        result = rng.choice(["승", "승", "패", "무"]) if status == "완료" else None
        cur = conn.execute(
            "INSERT INTO schedule (date, time, kind, place, opponent, venue_fee, status, result) "
            "VALUES (?, '09:00', '경기', ?, ?, 0, ?, ?)",
            (d, PLACES[n % len(PLACES)], OPPONENTS[n], status, result),
        )
        sched_ids[d + "경기"] = cur.lastrowid
    for n, d in enumerate(PRACTICE_DATES):
        status = "완료" if d < AS_OF else "예정"
        cur = conn.execute(
            "INSERT INTO schedule (date, time, kind, place, venue_fee, status) VALUES (?, '14:00', '연습', ?, 200000, ?)",
            (d, PLACES[(n + 1) % len(PLACES)], status),
        )
        sched_ids[d + "연습"] = cur.lastrowid
        if status == "완료":
            conn.execute(
                'INSERT INTO "transaction" (date, type, category, amount, memo, schedule_id) '
                "VALUES (?, '지출', '대관료', 200000, ?, ?)",
                (d, f"연습 대관료 ({d})", cur.lastrowid),
            )

    # 리그비 지출
    conn.execute(
        'INSERT INTO "transaction" (date, type, category, amount, memo) VALUES (?, \'지출\', \'리그비\', 3700000, \'연간 리그 참가비\')',
        ("2026-03-02",),
    )

    # 회비 납부 (납부 → 수입 거래 동기화)
    def pay(member_id, dues_round, amount, paid_at):
        name = MEMBERS[member_id - 1][0]
        t = conn.execute(
            'INSERT INTO "transaction" (date, type, category, amount, memo) VALUES (?, \'수입\', \'회비\', ?, ?)',
            (paid_at, amount, f"{name} 회비"),
        ).lastrowid
        conn.execute(
            "INSERT INTO payment (member_id, dues_id, round, amount, paid_at, transaction_id) VALUES (?, ?, ?, ?, ?, ?)",
            (member_id, member_id, dues_round, amount, paid_at, t),
        )

    for i in range(1, len(MEMBERS) + 1):
        if i in INSTALLMENT_MEMBERS:
            for rnd, month in enumerate(DUE_MONTHS, start=1):
                if month <= 7:  # 기준일(10월) 기준 1~3회차 납부, 11월분은 기한 전
                    pay(i, rnd, 50000, f"2026-{month:02d}-{rng.randint(3, 20):02d}")
        elif i not in UNPAID_MEMBERS:
            pay(i, 1, 200000, f"2026-01-{rng.randint(5, 28):02d}")

    # 완료된 일정의 참석 기록 (회원마다 참석 성향이 다르다)
    tendency = {i: rng.uniform(0.45, 0.98) for i in range(1, len(MEMBERS) + 1)}
    for key, sid in sched_ids.items():
        if conn.execute("SELECT status FROM schedule WHERE id = ?", (sid,)).fetchone()[0] != "완료":
            continue
        for i in range(1, len(MEMBERS) + 1):
            attended = 1 if rng.random() < tendency[i] else 0
            conn.execute(
                "INSERT INTO attendance (schedule_id, member_id, attended) VALUES (?, ?, ?)", (sid, i, attended)
            )

    conn.commit()
    if own:
        conn.close()


if __name__ == "__main__":
    seed()
    print("가상 데이터를 생성했습니다.")
