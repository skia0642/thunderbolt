from datetime import date

import pandas as pd
import streamlit as st

from db.connection import connect
from services import payments
from services.attendance import attendance_history, member_attendance_rows
from services.dues import member_dues_rows
from services.errors import ValidationError
from services.members import POSITIONS, PAY_TYPES, STATUSES, create_member, delete_member, update_member
from services.settings import as_of
from ui_utils import comma_style, flash, page_header, readonly_notice, show_flash, view_year, won

page_header("회원", "회원 정보와 회비 납부·참석 현황을 관리합니다.")
show_flash()


def report(e: ValidationError) -> None:
    for m in e.messages:
        st.error(m)


def member_form(key: str, m: dict | None = None, submit_label: str = "저장", clear: bool = False):
    """회원 입력 폼. 제출되면 입력값 dict를, 아니면 None을 돌려준다."""
    m = m or {}
    with st.form(key, clear_on_submit=clear):
        c1, c2 = st.columns(2)
        name = c1.text_input("이름", value=m.get("name", ""), max_chars=20)
        phone = c2.text_input("연락처", value=m.get("phone", ""), placeholder="010-0000-0000")
        pos_options = [""] + POSITIONS
        pos = m.get("position") or ""
        if pos not in pos_options:
            pos_options.append(pos)
        position = c1.selectbox("포지션", pos_options, index=pos_options.index(pos))
        back = c2.number_input("등번호", min_value=0, max_value=99, step=1, value=m.get("back_number"))
        joined = c1.date_input("가입일", value=date.fromisoformat(m["joined_at"]) if m.get("joined_at") else None)
        status = c2.radio("상태", STATUSES, index=STATUSES.index(m.get("status", "활동")), horizontal=True,
                          help="휴면 회원은 회비가 부과되지 않습니다.")
        pay_type = c1.selectbox("납부방식", PAY_TYPES, index=PAY_TYPES.index(m.get("pay_type", "일괄")),
                                help="분납은 1·4·7·11월 4회(회당 50,000원)")
        ok = st.form_submit_button(submit_label, type="primary")
    if not ok:
        return None
    return {"name": name, "phone": phone, "position": position, "back_number": back,
            "joined_at": joined, "status": status, "pay_type": pay_type}


with connect() as conn:
    year, readonly = view_year(conn)
    today = as_of(conn, year)
    dues = {r["member_id"]: r for r in member_dues_rows(conn, year)}
    att = {r["member_id"]: r for r in member_attendance_rows(conn, year)}
    members = [dict(r) for r in conn.execute("SELECT * FROM member ORDER BY id")]
    if readonly:
        readonly_notice(year)

    tab_list, tab_new, tab_status = st.tabs(["회원 목록", "회원 등록", "미납·참석 현황"])

    # ---- 목록 / 상세 -----------------------------------------------------------
    with tab_list:
        f1, f2, f3 = st.columns([2, 1, 1])
        q = f1.text_input("이름 검색", placeholder="이름 일부를 입력")
        status_f = f2.selectbox("상태", ["전체", *STATUSES])
        pay_f = f3.selectbox("납부 상태", ["전체", "완납", "분납중", "미납", "연체", "면제"])

        rows = []
        for m in members:
            d, a = dues[m["id"]], att[m["id"]]
            if q and q.strip() not in m["name"]:
                continue
            if status_f != "전체" and m["status"] != status_f:
                continue
            if pay_f != "전체" and d["pay_status"] != pay_f:
                continue
            rows.append({"이름": m["name"], "포지션": m["position"], "등번호": m["back_number"],
                         "상태": m["status"], "납부방식": m["pay_type"], "납부액": d["paid"], "미납액": d["unpaid"],
                         "납부 상태": d["pay_status"], "납부율(%)": d["rate"],
                         "도래분 납부율(%)": d["rate_to_date"] if m["pay_type"] == "분납" else None,
                         "참석율(%)": a["rate"]})
        st.caption(f"{len(rows)}명")
        if rows:
            df = pd.DataFrame(rows)
            df["등번호"] = df["등번호"].astype("Int64")  # 비어 있는 회원이 있어도 1.000000처럼 보이지 않게 한다
            rate_cfg = lambda label, help=None: st.column_config.ProgressColumn(
                label, format="%.1f%%", min_value=0, max_value=100, help=help, width="small")
            st.dataframe(comma_style(df, {"납부액": 0, "미납액": 0}, badges=["상태", "납부 상태"]),
                         hide_index=True,
                         column_config={"납부율(%)": rate_cfg("납부율", "연간 부과액 대비 납부액"),
                                        "도래분 납부율(%)": rate_cfg("도래분 납부율", "분납자만 표시 · 기한이 도래한 회차 대비 납부 비율"),
                                        "참석율(%)": rate_cfg("참석율")})
        else:
            st.info("조건에 맞는 회원이 없습니다.")

        st.divider()
        by_id = {m["id"]: m for m in members}
        if not members:
            st.info("등록된 회원이 없습니다. '회원 등록' 탭에서 추가하세요.")
        else:
            sel = st.selectbox("회원 선택 (상세·납부·수정)", list(by_id), key="member_sel",
                               format_func=lambda i: f"{by_id[i]['name']} ({by_id[i]['status']})")
            m = by_id[sel]
            d = dues[sel]
            st.subheader(f"{m['name']}")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("부과액", won(d["due"]))
            k2.metric("납부액", won(d["paid"]))
            k3.metric("미납액", won(d["unpaid"]))
            k4.metric("납부 상태", d["pay_status"])
            if m["pay_type"] == "분납" and d["rate_to_date"] is not None:
                st.caption(f"기한 도래분 납부율 {d['rate_to_date']}% "
                           f"(도래분 {d['due_to_date']:,}원 중 {d['paid_to_date']:,}원 납부)")

            t_pay, t_att, t_edit = st.tabs(["납부", "참석 이력", "정보 수정·삭제"])

            with t_pay:
                if m["status"] == "휴면":
                    st.info("휴면 회원은 회비 부과 대상에서 제외됩니다. 납부 기록은 활동으로 변경한 뒤 가능합니다.")
                sched = payments.payment_schedule(conn, sel, year)
                st.dataframe(comma_style(pd.DataFrame([{
                    "회차": r["label"], "납부 기한": r["deadline"].isoformat(), "금액": r["amount"],
                    "상태": r["state"], "납부일": r["paid_at"] or "-"} for r in sched]), {"금액": 0}, badges=["상태"]),
                    hide_index=True)
                if any(r["state"] == "연체" for r in sched) and m["status"] == "활동":
                    st.warning("기한이 지난 미납 회차가 있습니다.")
                if not readonly:
                    c_pay, c_cancel = st.columns(2)
                    unpaid = [r for r in sched if not r["paid"]]
                    with c_pay:
                        if unpaid and m["status"] == "활동":
                            rnd = st.selectbox("납부할 회차", [r["round"] for r in unpaid], key=f"pr_{sel}",
                                               format_func=lambda x: next(r["label"] for r in sched if r["round"] == x))
                            paid_at = st.date_input("납부일", value=today, key=f"pd_{sel}")
                            if st.button("납부 기록", type="primary", key=f"pb_{sel}"):
                                try:
                                    payments.pay(conn, sel, rnd, paid_at)
                                    flash(f"{m['name']} 회원 {next(r['label'] for r in sched if r['round'] == rnd)} 납부를 기록했습니다.")
                                    st.rerun()
                                except ValidationError as e:
                                    report(e)
                        elif not unpaid:
                            st.success("모든 회차가 납부되었습니다.")
                    with c_cancel:
                        paid_rows = [r for r in sched if r["paid"]]
                        if paid_rows:
                            crnd = st.selectbox("취소할 회차", [r["round"] for r in paid_rows], key=f"cr_{sel}",
                                                format_func=lambda x: next(r["label"] for r in sched if r["round"] == x))
                            if st.button("납부 취소", key=f"cb_{sel}"):
                                try:
                                    payments.cancel_payment(conn, sel, crnd)
                                    flash("납부를 취소했습니다. 연동된 수입 내역도 삭제되었습니다.", "warning")
                                    st.rerun()
                                except ValidationError as e:
                                    report(e)

            with t_att:
                hist = attendance_history(conn, sel, year)
                a = att[sel]
                a1, a2, a3 = st.columns(3)
                a1.metric("전체 참석율", f"{a['rate']}%" if a["rate"] is not None else "-")
                a2.metric("경기 참석율", f"{a['game_rate']}%" if a["game_rate"] is not None else "-")
                a3.metric("연습 참석율", f"{a['practice_rate']}%" if a["practice_rate"] is not None else "-")
                if hist:
                    st.dataframe(comma_style(pd.DataFrame([{
                        "날짜": h["date"], "구분": h["kind"], "상대/장소": h["opponent"] or h["place"] or "-",
                        "출석": "참석" if h["attended"] else "결석"} for h in hist]), badges=["구분", "출석"]),
                        hide_index=True)
                else:
                    st.info("종료된 일정이 없습니다.")

            with t_edit:
                if readonly:
                    st.info("지난 연도를 보는 중에는 회원 정보를 수정하거나 삭제할 수 없습니다.")
                else:
                    data = member_form(f"edit_{sel}", m, "수정 저장")
                    if data:
                        try:
                            update_member(conn, sel, data)
                            flash("회원 정보를 수정했습니다.")
                            st.rerun()
                        except ValidationError as e:
                            report(e)
                    st.divider()
                    st.caption("회원을 삭제하면 납부·참석 기록과 연동된 수입 내역도 함께 삭제됩니다. 되돌릴 수 없습니다.")
                    sure = st.checkbox(f"{m['name']} 회원을 삭제합니다", key=f"del_ok_{sel}")
                    if st.button("회원 삭제", disabled=not sure, key=f"del_{sel}"):
                        delete_member(conn, sel)
                        flash(f"{m['name']} 회원을 삭제했습니다.", "warning")
                        st.rerun()

    # ---- 등록 ------------------------------------------------------------------
    with tab_new:
        if readonly:
            st.info("지난 연도를 보는 중에는 회원을 등록할 수 없습니다.")
        else:
            data = member_form("new_member", submit_label="회원 등록", clear=True)
            if data:
                try:
                    create_member(conn, data)
                    flash(f"{data['name'].strip()} 회원을 등록했습니다.")
                    st.rerun()
                except ValidationError as e:
                    report(e)

    # ---- 미납 / 참석 하위 --------------------------------------------------------
    with tab_status:
        st.subheader("미납자")
        unpaid_rows = [{"이름": r["name"], "납부방식": r["pay_type"], "납부액": r["paid"], "미납액": r["unpaid"],
                        "상태": r["pay_status"], "연체 회차": ", ".join(f"{x}회차" for x in r["overdue_rounds"]) or "-"}
                       for r in dues.values() if r["status"] == "활동" and r["unpaid"] > 0]
        if unpaid_rows:
            st.dataframe(comma_style(pd.DataFrame(unpaid_rows), {"납부액": 0, "미납액": 0}, badges=["상태"]), hide_index=True)
        else:
            st.success("미납자가 없습니다.")
        st.subheader("참석율 하위 5명 (활동 회원)")
        low = sorted((r for r in att.values() if r["status"] == "활동" and r["rate"] is not None),
                     key=lambda r: r["rate"])[:5]
        if low:
            st.dataframe(pd.DataFrame([{"이름": r["name"], "참석 횟수": r["attended"], "참석율(%)": r["rate"]} for r in low]),
                         hide_index=True)
        else:
            st.info("종료된 일정이 없어 참석율을 계산할 수 없습니다.")
