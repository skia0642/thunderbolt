from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from db.connection import connect
from services import payments, transactions
from services.dues import member_dues_rows
from services.errors import ValidationError
from services.finance import finance_summary
from services.settings import as_of, create_year, get_settings
from theme import EXPENSE, INCOME
from ui_utils import (comma_style, flash, money_input, monthly_chart, page_header, readonly_notice, show_flash,
                      view_year, won)

page_header("회비", "수입·지출 내역과 잔액, 예비비를 확인합니다.")
show_flash()


def report(e: ValidationError) -> None:
    for m in e.messages:
        st.error(m)


with connect() as conn:
    year, readonly = view_year(conn)
    s = get_settings(conn, year)
    f = finance_summary(conn, year)
    today = as_of(conn, year)
    if readonly:
        readonly_notice(year)

    c1, c2, c3 = st.columns(3)
    c1.metric("현재 잔액", won(f["balance"]))
    c2.metric("차년도 예비비", won(f["reserve"]))
    c3.metric("예비비 제외 사용 가능 잔액", won(f["usable_balance"]),
              help="현재 잔액 − 예비비. 아직 걷지 못한 회비는 포함되지 않아 음수일 수 있습니다.")
    c4, c5, c6 = st.columns(3)
    c4.metric("총수입", won(f["income"]))
    c5.metric("총지출", won(f["expense"]))
    c6.metric("연말 예상 잔액", won(f["projected_year_end"]))
    if f["projected_year_end"] < f["reserve"]:
        st.warning(f"연말 예상 잔액이 예비비보다 {f['reserve'] - f['projected_year_end']:,}원 부족합니다.")

    tab_list, tab_new, tab_chart, tab_year = st.tabs(["수입·지출 내역", "수입·지출 등록", "월별 차트", "연말 이월·새 연도"])

    # ---- 내역 ---------------------------------------------------------------------
    with tab_list:
        f1, f2, f3, f4 = st.columns(4)
        start = f1.date_input("시작일", value=date(s["year"], 1, 1), min_value=date(s["year"], 1, 1),
                              max_value=date(s["year"], 12, 31), key="tx_start")
        end = f2.date_input("종료일", value=date(s["year"], 12, 31), min_value=date(s["year"], 1, 1),
                            max_value=date(s["year"], 12, 31), key="tx_end")
        type_f = f3.selectbox("구분", ["전체", "수입", "지출"], key="tx_type")
        cats = ["전체", *dict.fromkeys([*transactions.INCOME_CATEGORIES, *transactions.EXPENSE_CATEGORIES])]
        cat_f = f4.selectbox("분류", cats, key="tx_cat")
        if start > end:
            st.error("시작일이 종료일보다 늦습니다.")
            rows = []
        else:
            rows = transactions.list_transactions(
                conn, start, end, None if type_f == "전체" else type_f, None if cat_f == "전체" else cat_f, year)
        if rows:
            df = pd.DataFrame([{"ID": r["id"], "일자": r["date"], "구분": r["type"], "분류": r["category"],
                                "금액": r["amount"], "메모": r["memo"] or "", "연동": r["source"]} for r in rows])
            st.dataframe(comma_style(df, {"금액": 0}, badges=["구분", "연동"]), hide_index=True)
            inc = sum(r["amount"] for r in rows if r["type"] == "수입")
            exp = sum(r["amount"] for r in rows if r["type"] == "지출")
            st.caption(f"{len(rows):,}건 · 수입 {inc:,}원 · 지출 {exp:,}원")
        else:
            st.info("조건에 맞는 내역이 없습니다.")

        manual = [r for r in transactions.list_transactions(conn, year=year) if r["source"] == "수동"]
        st.divider()
        st.caption("수정·삭제는 직접 입력한 내역만 가능합니다. 납부 연동 내역은 회원 화면에서, "
                   "대관료 연동 내역은 일정 화면에서 바꿉니다.")
        if readonly:
            st.caption("지난 연도는 조회만 가능합니다.")
        elif manual:
            by_manual = {r["id"]: r for r in manual}
            tid = st.selectbox("수정할 내역", list(by_manual), key="tx_edit_sel", format_func=lambda i: (
                f"{by_manual[i]['date']} {by_manual[i]['type']} {by_manual[i]['category']} {by_manual[i]['amount']:,}원"))
            r = by_manual[tid]
            with st.form(f"tx_edit_{tid}"):
                e1, e2, e3, e4 = st.columns(4)
                ed = e1.date_input("일자", value=date.fromisoformat(r["date"]), min_value=date(s["year"], 1, 1),
                                   max_value=date(s["year"], 12, 31))
                et = e2.radio("구분", ["수입", "지출"], index=["수입", "지출"].index(r["type"]), horizontal=True)
                ec_opts = list(dict.fromkeys([*transactions.INCOME_CATEGORIES, *transactions.EXPENSE_CATEGORIES]))
                ec = e3.selectbox("분류", ec_opts, index=ec_opts.index(r["category"]))
                ea = money_input("금액", r["amount"], e4)
                em = st.text_input("메모", value=r["memo"] or "", max_chars=100)
                if st.form_submit_button("수정 저장", type="primary"):
                    try:
                        transactions.update_transaction(conn, tid, {"date": ed, "type": et, "category": ec,
                                                                    "amount": ea, "memo": em})
                        flash("내역을 수정했습니다.")
                        st.rerun()
                    except ValidationError as e:
                        report(e)
            sure = st.checkbox("삭제 확인", key=f"txdel_ok_{tid}")
            if st.button("내역 삭제", disabled=not sure, key=f"txdel_{tid}"):
                transactions.delete_transaction(conn, tid)
                flash("내역을 삭제했습니다.", "warning")
                st.rerun()
        else:
            st.info("직접 입력한 내역이 없습니다.")

    # ---- 등록 ---------------------------------------------------------------------
    with tab_new:
        kind = st.radio("구분", ["수입", "지출"], horizontal=True, key="new_tx_type", disabled=readonly)
        if readonly:
            st.info("지난 연도를 보는 중에는 내역을 등록할 수 없습니다.")
            cat = None
        elif kind == "수입":
            cat = st.selectbox("분류", transactions.INCOME_CATEGORIES, key="new_inc_cat")
            if cat == "회비":
                st.caption("회비 수입은 회원 납부로 기록합니다. 회원의 납부 현황과 수입 내역이 함께 갱신됩니다.")
                dues = [r for r in member_dues_rows(conn) if r["status"] == "활동" and r["unpaid"] > 0]
                if not dues:
                    st.success("미납 회원이 없습니다.")
                else:
                    by_dues = {r["member_id"]: r for r in dues}
                    mid = st.selectbox("납부 회원", list(by_dues), key="new_pay_member",
                                       format_func=lambda i: f"{by_dues[i]['name']} (미납 {by_dues[i]['unpaid']:,}원)")
                    sched = [r for r in payments.payment_schedule(conn, mid) if not r["paid"]]
                    rnd = st.selectbox("회차", [r["round"] for r in sched], key=f"new_pay_round_{mid}",
                                       format_func=lambda x: next(f"{r['label']} · {r['amount']:,}원" for r in sched if r["round"] == x))
                    pd_ = st.date_input("납부일", value=today, min_value=date(s["year"], 1, 1),
                                        max_value=date(s["year"], 12, 31), key="new_pay_date")
                    if st.button("납부 등록", type="primary", key="new_pay_btn"):
                        try:
                            payments.pay(conn, mid, rnd, pd_)
                            flash(f"{by_dues[mid]['name']} 회원의 회비 납부를 등록했습니다.")
                            st.rerun()
                        except ValidationError as e:
                            report(e)
        else:
            cat = st.selectbox("분류", transactions.EXPENSE_CATEGORIES, key="new_exp_cat")
        if not readonly and not (kind == "수입" and cat == "회비"):
            with st.form("new_tx", clear_on_submit=True):
                n1, n2 = st.columns(2)
                nd = n1.date_input("일자", value=today, min_value=date(s["year"], 1, 1), max_value=date(s["year"], 12, 31))
                na = money_input("금액", 10_000, n2)
                nm = st.text_input("메모", max_chars=100)
                if st.form_submit_button("등록", type="primary"):
                    try:
                        transactions.add_transaction(conn, {"date": nd, "type": kind, "category": cat,
                                                            "amount": na, "memo": nm})
                        flash(f"{kind} 내역을 등록했습니다.")
                        st.rerun()
                    except ValidationError as e:
                        report(e)
            if kind == "지출" and cat == "대관료":
                st.caption("연습 대관료는 일정에서 연습을 '완료 처리'하면 자동 등록됩니다. 이 입력은 그 외 대관료용입니다.")

    # ---- 차트 ---------------------------------------------------------------------
    with tab_chart:
        monthly = pd.DataFrame(transactions.monthly_summary(conn, year)).set_index("월")
        if monthly.to_numpy().sum() == 0:
            st.info("표시할 내역이 없습니다.")
        else:
            st.altair_chart(monthly_chart(monthly), width="stretch")
            st.markdown("**잔액 추이** (점선: 차년도 예비비)")
            net = (monthly["수입"] - monthly["지출"]).cumsum() + f["carry_over"]
            upto = min(12, today.month)
            trend = pd.DataFrame({"월": list(monthly.index[:upto]), "잔액": list(net.iloc[:upto])})
            line = alt.Chart(trend).mark_line(point=True, color=INCOME).encode(
                x=alt.X("월:N", sort=list(monthly.index), axis=alt.Axis(labelAngle=0, title=None)),
                y=alt.Y("잔액:Q", axis=alt.Axis(format=",.0f", title="잔액(원)")),
                tooltip=["월", alt.Tooltip("잔액:Q", format=",.0f")])
            rule = alt.Chart(pd.DataFrame({"예비비": [f["reserve"]]})).mark_rule(
                color=EXPENSE, strokeDash=[6, 4]).encode(y="예비비:Q")
            st.altair_chart((line + rule).properties(height=240), width="stretch")
            st.dataframe(comma_style(monthly.reset_index(), {"수입": 0, "지출": 0}), hide_index=True)

    # ---- 이월 / 새 연도 -----------------------------------------------------------------
    with tab_year:
        if readonly:
            st.info("연말 이월과 새 연도 만들기는 최신 연도에서만 할 수 있습니다.")
        else:
            st.write(f"**{s['year']}년 연말 이월**")
            y1, y2, y3 = st.columns(3)
            y1.metric("현재 잔액", won(f["balance"]))
            y2.metric("연말 예상 잔액 (이월 예정액)", won(f["projected_year_end"]))
            y3.metric("그중 예비비", won(f["reserve"]))
            st.caption("연말 잔액은 전액 차년도 이월 잔액이 됩니다. 연말에는 현재 잔액과 연말 예상 잔액이 같아지고, "
                       "연말 전에 미리 만든다면 미수 회비·남은 지출이 반영된 '연말 예상 잔액'을 기준으로 삼는 편이 정확합니다. "
                       "금액은 회장단이 직접 확정하며, 이월 금액의 사용처는 프로그램이 제한하지 않습니다.")
            basis = st.radio("이월 잔액 기준", ["현재 잔액", "연말 예상 잔액"], horizontal=True, key="carry_basis")
            suggested = f["balance"] if basis == "현재 잔액" else f["projected_year_end"]
            with st.form("new_year"):
                ny = st.number_input("새 연도", min_value=s["year"] + 1, max_value=s["year"] + 10, value=s["year"] + 1, step=1)
                carry = money_input(f"이월 잔액 ({basis} 기준 제안, 수정 가능)", max(0, suggested), key=f"carry_{basis}")
                q1, q2 = st.columns(2)
                reserve = money_input("차년도 예비비", s["reserve"], q1)
                league = money_input("리그비", s["league_fee"], q2)
                dues_ = money_input("연 회비(인당)", s["annual_dues"], q1)
                venue = money_input("연습 대관료", s["venue_fee"], q2)
                games = q1.number_input("리그 경기 수", min_value=0, max_value=100, value=s["league_games"])
                sure = st.checkbox("새 연도를 만들면 대시보드·내역이 새 연도 기준으로 바뀝니다(지난 연도는 사이드바에서 조회). 확인했습니다.")
                if st.form_submit_button("새 연도 만들기", type="primary"):
                    if not sure:
                        st.error("확인란을 체크하세요.")
                    else:
                        try:
                            create_year(conn, int(ny), {"carry_over": carry, "reserve": reserve, "league_fee": league,
                                                        "annual_dues": dues_, "venue_fee": venue, "league_games": games})
                            flash(f"{int(ny)}년을 만들었습니다. 이월 잔액 {int(carry):,}원.")
                            st.session_state["_next_view_year"] = int(ny)
                            st.rerun()
                        except ValidationError as e:
                            report(e)
