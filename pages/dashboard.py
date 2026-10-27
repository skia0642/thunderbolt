import html

import pandas as pd
import streamlit as st

from db.connection import connect
from services.attendance import average_attendance_rate
from services.dues import member_dues_rows, overall_payment_rate
from services.finance import finance_summary
from services.schedule import remaining_counts, remaining_schedule
from services.settings import as_of
from services.transactions import monthly_summary
from theme import badge_html
from ui_utils import comma_style, monthly_chart, page_header, view_year, won

with connect() as conn:
    year, readonly = view_year(conn)
    f = finance_summary(conn, year)
    pay_rate = overall_payment_rate(conn, year)
    att_rate = average_attendance_rate(conn, year)
    counts = remaining_counts(conn, year)
    upcoming = remaining_schedule(conn, year)
    today = as_of(conn, year)
    unpaid = [r for r in member_dues_rows(conn, year) if r["status"] == "활동" and r["unpaid"] > 0]
    monthly = pd.DataFrame(monthly_summary(conn, year)).set_index("월")

page_header("대시보드", f"{f['year']}년{' (지난 연도 · 조회 전용)' if readonly else ''} · 기준일 {today.isoformat()}")


def pct(v) -> str:
    return "-" if v is None else f"{v:.1f}%"


# ---- 핵심 숫자 ---------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("현재 잔액", won(f["balance"]), help="이월 잔액 + 총수입 − 총지출")
c2.metric("차년도 예비비", won(f["reserve"]), help="연내 사용하지 않고 차년도로 이월하는 금액")
gap = f["projected_year_end"] - f["reserve"]
# delta 문자열이 부호로 시작해야 화살표 방향과 색이 맞게 표시된다. 0이면 화살표를 쓰지 않는다.
c3.metric("연말 예상 잔액", won(f["projected_year_end"]),
          delta=f"{gap:+,}원 (예비비 대비)" if gap else "예비비와 동일",
          delta_color="normal" if gap else "off", delta_arrow="auto" if gap else "off",
          help="미수 회비 전액 수금과 남은 리그비·예정 연습 대관료 지출을 반영한 예상치")

c4, c5, c6 = st.columns(3)
c4.metric("총수입", won(f["income"]))
c5.metric("총지출", won(f["expense"]))
c6.metric("연습 가능 횟수 (연간)", f"{f['max_practices']}회",
          delta=f"완료 {f['practices_done']}회 · 추가 편성 {f['additional_practices_possible']}회 가능",
          delta_color="off", delta_arrow="off", help="(이월 + 부과 회비 − 리그비 − 예비비) ÷ 대관료")

# ---- 납부율 · 참석율 · 미납 -------------------------------------------------------------
p1, p2, p3 = st.columns(3)
with p1, st.container(border=True):
    st.markdown("**회비 납부율**")
    st.markdown(f'<div class="big-number">{pct(pay_rate)}</div>', unsafe_allow_html=True)
    st.progress(min(1.0, (pay_rate or 0) / 100))
with p2, st.container(border=True):
    st.markdown("**평균 참석율**")
    st.markdown(f'<div class="big-number">{pct(att_rate)}</div>', unsafe_allow_html=True)
    st.progress(min(1.0, (att_rate or 0) / 100))
with p3, st.container(border=True):
    st.markdown("**미납 회원**")
    st.markdown(f'<div class="big-number">{len(unpaid):,}명</div>', unsafe_allow_html=True)
    st.caption(f"미납액 합계 {sum(r['unpaid'] for r in unpaid):,}원")

# ---- 일정 · 미납 ------------------------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.subheader("잔여 일정")
    st.caption(f"경기 {counts['경기']:,}건 · 연습 {counts['연습']:,}건")
    if upcoming:
        nxt = upcoming[0]
        days = (pd.Timestamp(nxt["date"]).date() - today).days
        dday = "오늘" if days == 0 else f"D-{days}"
        # 상대팀·장소는 사용자 입력이므로 HTML로 해석되지 않게 이스케이프한다.
        detail = html.escape(nxt["opponent"] or nxt["place"] or "")
        st.markdown(
            f'<div class="next-card"><div class="m">다음 일정</div>'
            f'<div class="d">{dday} · {html.escape(nxt["date"])}</div>'
            f'<div>{badge_html(nxt["kind"])}{detail}</div></div>', unsafe_allow_html=True)
        st.dataframe(comma_style(pd.DataFrame([{
            "날짜": r["date"], "구분": r["kind"], "장소": r["place"] or "-", "상대": r["opponent"] or "-"}
            for r in upcoming]), badges=["구분"]), hide_index=True)
    else:
        st.info("남은 일정이 없습니다.")
with right:
    st.subheader("미납자")
    if unpaid:
        top = sorted(unpaid, key=lambda r: -r["unpaid"])[:5]
        st.dataframe(comma_style(pd.DataFrame([{
            "이름": r["name"], "미납액": r["unpaid"], "상태": r["pay_status"]} for r in top]),
            {"미납액": 0}, badges=["상태"]), hide_index=True)
        if len(unpaid) > 5:
            st.caption(f"외 {len(unpaid) - 5}명 · 전체 목록은 회원 > 미납·참석 현황")
    else:
        st.success("미납자가 없습니다.")

# ---- 차트 -------------------------------------------------------------------------------
st.subheader("월별 수입·지출")
if monthly.to_numpy().sum() == 0:
    st.info("표시할 내역이 없습니다.")
else:
    st.altair_chart(monthly_chart(monthly), width="stretch")

with st.expander("연습 예산 계산 상세"):
    st.write(f"- 총 가용 재원(이월 + 부과 회비): {won(f['total_resources'])}")
    st.write(f"- 연습 가용 예산(재원 − 리그비 − 예비비): {won(f['practice_budget'])}")
    st.write(f"- 현재 기준 연습 가용액(잔액 − 예비비 − 잔여 리그비): {won(f['practice_available_now'])} "
             "· 아직 걷지 못한 회비는 반영되지 않은 금액입니다.")
    st.write(f"- 추가로 편성 가능한 연습: {f['additional_practices_possible']}회")
