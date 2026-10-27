from datetime import date, time

import pandas as pd
import streamlit as st

from db.connection import connect
from services.attendance import get_attendance, save_attendance
from services.errors import ValidationError
from services.schedule import (KINDS, RESULTS, STATUSES, create_schedule, delete_schedule,
                               remaining_counts, remaining_schedule, set_status, update_schedule)
from services.settings import as_of, get_settings
from ui_utils import (calendar_html, comma_style, flash, money_input, page_header, readonly_notice, show_flash,
                      view_year, won)

page_header("일정", "경기·연습 일정과 출석을 관리합니다. 연습을 완료 처리하면 대관료 지출이 자동 등록됩니다.")
show_flash()


def report(e: ValidationError) -> None:
    for m in e.messages:
        st.error(m)


def label(r) -> str:
    extra = r["opponent"] or r["place"] or ""
    return f"{r['date']} {r['kind']} {extra} [{r['status']}]".strip()


def schedule_form(key: str, today: date, year: int, default_fee: int, r: dict | None = None, submit: str = "저장"):
    r = r or {}
    with st.form(key, clear_on_submit=r == {}):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("날짜", value=date.fromisoformat(r["date"]) if r.get("date") else today,
                          min_value=date(year, 1, 1), max_value=date(year, 12, 31))
        hh, mm = (r.get("time") or "09:00").split(":")
        t = c2.time_input("시간", value=time(int(hh), int(mm)), step=1800)
        kind = c3.radio("구분", KINDS, index=KINDS.index(r.get("kind", "경기")), horizontal=True)
        place = c1.text_input("장소", value=r.get("place") or "", max_chars=50)
        opponent = c2.text_input("상대팀 (경기)", value=r.get("opponent") or "", max_chars=30)
        fee = money_input("대관료 (연습)", r.get("venue_fee") or default_fee, c3,
                          help="연습을 '완료'로 바꾸면 이 금액이 지출로 자동 등록됩니다.")
        status = c1.selectbox("상태", STATUSES, index=STATUSES.index(r.get("status", "예정")))
        res_opts = ["", *RESULTS]
        result = c2.selectbox("경기 결과", res_opts, index=res_opts.index(r.get("result") or ""))
        ok = st.form_submit_button(submit, type="primary")
    if not ok:
        return None
    return {"date": d, "time": t.strftime("%H:%M"), "kind": kind, "place": place, "opponent": opponent,
            "venue_fee": fee, "status": status, "result": result or None}


with connect() as conn:
    year, readonly = view_year(conn)
    s = get_settings(conn, year)
    today = as_of(conn, year)
    counts = remaining_counts(conn, year)
    remaining = remaining_schedule(conn, year)
    all_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM schedule WHERE strftime('%Y', date) = ? ORDER BY date, time", (str(year),))]
    members = [dict(r) for r in conn.execute("SELECT id, name FROM member WHERE status = '활동' ORDER BY id")]
    if readonly:
        readonly_notice(year)

    tab_rem, tab_all, tab_new, tab_att = st.tabs(["잔여 일정", "전체 일정", "일정 등록", "출석 체크"])

    # ---- 잔여 -------------------------------------------------------------------
    with tab_rem:
        st.caption(f"기준일 {today.isoformat()} 이후")
        c1, c2 = st.columns(2)
        c1.metric("잔여 경기", f"{counts['경기']:,}건")
        c2.metric("잔여 연습", f"{counts['연습']:,}건")
        if remaining:
            st.dataframe(comma_style(pd.DataFrame([{
                "날짜": r["date"], "시간": r["time"], "구분": r["kind"], "장소": r["place"] or "-",
                "상대": r["opponent"] or "-", "대관료": r["venue_fee"]} for r in remaining]), {"대관료": 0}, badges=["구분"]),
                hide_index=True)
        else:
            st.info("남은 일정이 없습니다.")

    # ---- 전체 + 수정 ----------------------------------------------------------------
    with tab_all:
        f1, f2 = st.columns(2)
        kind_f = f1.selectbox("구분", ["전체", *KINDS], key="sf_kind")
        stat_f = f2.selectbox("상태", ["전체", *STATUSES], key="sf_status")
        shown = [r for r in all_rows if (kind_f == "전체" or r["kind"] == kind_f)
                 and (stat_f == "전체" or r["status"] == stat_f)]
        view = st.radio("보기", ["목록", "달력"], horizontal=True, key="sched_view")
        if view == "달력":
            month = st.selectbox("월", list(range(1, 13)), index=min(today.month, 12) - 1, key="cal_month",
                                 format_func=lambda m: f"{year}년 {m}월")
            st.markdown(calendar_html(shown, year, month), unsafe_allow_html=True)
            in_month = sum(1 for r in shown if r["date"].startswith(f"{year}-{month:02d}"))
            st.caption(f"{month}월 일정 {in_month}건" if in_month else f"{month}월에는 일정이 없습니다.")
        elif shown:
            st.dataframe(comma_style(pd.DataFrame([{
                "날짜": r["date"], "시간": r["time"], "구분": r["kind"], "장소": r["place"] or "-",
                "상대": r["opponent"] or "-", "대관료": r["venue_fee"], "상태": r["status"],
                "결과": r["result"] or "-"} for r in shown]), {"대관료": 0}, badges=["구분", "상태"]), hide_index=True)
        else:
            st.info("조건에 맞는 일정이 없습니다.")

        if all_rows and not readonly:
            st.divider()
            by_all = {r["id"]: r for r in all_rows}
            sid = st.selectbox("수정할 일정", list(by_all), format_func=lambda i: label(by_all[i]), key="edit_sid")
            r = by_all[sid]
            data = schedule_form(f"edit_sched_{sid}", today, s["year"], s["venue_fee"], r, "수정 저장")
            if data:
                try:
                    warn = update_schedule(conn, sid, data)
                    flash("일정을 수정했습니다.")
                    if warn:
                        flash(warn, "warning")
                    st.rerun()
                except ValidationError as e:
                    report(e)
            b1, b2, b3 = st.columns(3)
            if r["status"] != "완료" and b1.button("완료 처리", key=f"done_{sid}"):
                msg = "연습 대관료 지출이 자동 등록되었습니다." if r["kind"] == "연습" and r["venue_fee"] else ""
                set_status(conn, sid, "완료")
                flash(f"완료 처리했습니다. {msg}")
                st.rerun()
            if r["status"] != "취소" and b2.button("일정 취소", key=f"cancel_{sid}"):
                set_status(conn, sid, "취소")
                flash("일정을 취소했습니다.", "warning")
                st.rerun()
            with b3:
                sure = st.checkbox("삭제 확인", key=f"sdel_ok_{sid}")
                if st.button("일정 삭제", disabled=not sure, key=f"sdel_{sid}"):
                    delete_schedule(conn, sid)
                    flash("일정을 삭제했습니다. 연동된 대관료 지출도 삭제되었습니다.", "warning")
                    st.rerun()

    # ---- 등록 -----------------------------------------------------------------------
    with tab_new:
        if readonly:
            st.info("지난 연도를 보는 중에는 일정을 등록할 수 없습니다.")
        else:
            data = schedule_form("new_sched", today, s["year"], s["venue_fee"], None, "일정 등록")
            if data:
                try:
                    _, warn = create_schedule(conn, data)
                    flash("일정을 등록했습니다.")
                    if warn:
                        flash(warn, "warning")
                    st.rerun()
                except ValidationError as e:
                    report(e)

    # ---- 출석 -----------------------------------------------------------------------
    with tab_att:
        done = [r for r in all_rows if r["status"] == "완료"]
        if readonly:
            st.info("지난 연도의 출석은 회원 화면의 '참석 이력'에서 조회할 수 있습니다.")
        elif not done:
            st.info("완료된 일정이 없습니다. 일정을 '완료 처리'하면 출석을 기록할 수 있습니다.")
        else:
            by_done = {r["id"]: r for r in done}
            ids = list(reversed(list(by_done)))
            sid = st.selectbox("일정 선택 (완료된 일정)", ids, format_func=lambda i: label(by_done[i]), key="att_sid")
            saved = get_attendance(conn, sid)
            keys = {m["id"]: f"att_{sid}_{m['id']}" for m in members}

            def set_all(value: bool, ks=tuple(keys.values())):
                for k in ks:
                    st.session_state[k] = value

            a1, a2, _ = st.columns([1, 1, 4])
            a1.button("전체 참석", on_click=set_all, args=(True,), key=f"all_on_{sid}")
            a2.button("전체 결석", on_click=set_all, args=(False,), key=f"all_off_{sid}")
            cols = st.columns(4)
            for i, m in enumerate(members):
                cols[i % 4].checkbox(m["name"], value=saved.get(m["id"], False), key=keys[m["id"]])
            marked = sum(1 for k in keys.values() if st.session_state.get(k))
            st.caption(f"참석 {marked}명 / 활동 회원 {len(members)}명")
            if st.button("출석 저장", type="primary", key=f"att_save_{sid}"):
                try:
                    save_attendance(conn, sid, {mid: bool(st.session_state.get(k)) for mid, k in keys.items()})
                    flash("출석을 저장했습니다.")
                    st.rerun()
                except ValidationError as e:
                    report(e)
