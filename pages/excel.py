import pandas as pd
import streamlit as st

from db.connection import connect
from services import excel
from services.errors import ValidationError
from ui_utils import comma_style, flash, page_header, readonly_notice, show_flash, view_year

page_header("엑셀", "회원 데이터를 엑셀로 올리고 내려받습니다.")
show_flash()


def steps(active: int) -> None:
    items = ["① 템플릿 받기", "② 업로드·검증 확인", "③ 정상 행 반영"]
    html = "".join(
        f'<div class="step {"done" if i < active else "on" if i == active else ""}"><b>{t}</b></div>'
        for i, t in enumerate(items))
    st.markdown(f'<div class="steps">{html}</div>', unsafe_allow_html=True)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
st.session_state.setdefault("upload_nonce", 0)

with connect() as conn:
    year, readonly = view_year(conn)
    tab_up, tab_down = st.tabs(["회원 업로드", "다운로드"])

    with tab_up:
        if readonly:
            readonly_notice(year)
        else:
            up_key = f"upload_{st.session_state['upload_nonce']}"
            steps(1 if st.session_state.get(up_key) is not None else 0)
            st.download_button("회원 업로드 템플릿 받기", excel.template_bytes(), "회원_업로드_템플릿.xlsx", XLSX)
            up = st.file_uploader("회원 엑셀 파일(.xlsx)", type=["xlsx"], key=up_key)
            if up is not None:
                try:
                    parsed = excel.parse_members(conn, up)
                except ValidationError as e:
                    for m in e.messages:
                        st.error(m)
                    parsed = None
                if parsed:
                    n_new = sum(p["action"] == "신규" for p in parsed)
                    n_upd = sum(p["action"] == "갱신" for p in parsed)
                    n_err = sum(p["action"] == "오류" for p in parsed)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("신규", f"{n_new:,}건")
                    m2.metric("갱신 (이름+연락처 동일)", f"{n_upd:,}건")
                    m3.metric("오류", f"{n_err:,}건")
                    df = pd.DataFrame([{"엑셀 행": p["row"], "이름": p["name"] or "", "결과": p["action"],
                                        "사유": p["reason"] or "-"} for p in parsed])
                    st.dataframe(comma_style(df, badges=["결과"]), hide_index=True,
                                 column_config={"사유": st.column_config.TextColumn("사유", width="large")})
                    if n_err:
                        st.warning(f"오류 {n_err}건은 반영되지 않습니다. 정상 {n_new + n_upd}건만 반영할 수 있습니다.")
                    if n_new + n_upd == 0:
                        st.error("반영할 수 있는 행이 없습니다. 파일을 수정해 다시 올려주세요.")
                    elif st.button(f"정상 {n_new + n_upd}건 반영", type="primary"):
                        result = excel.apply_members(conn, parsed)
                        flash(f"신규 {result['신규']}건, 갱신 {result['갱신']}건을 반영했습니다.")
                        for fail in result["실패"]:
                            flash(f"{fail['row']}행 {fail['name']}: {fail['reason']}", "error")
                        st.session_state["upload_nonce"] += 1
                        st.rerun()

    with tab_down:
        st.caption(f"{year}년 기준 데이터를 내려받습니다. 연도는 사이드바에서 바꿀 수 있습니다.")
        st.download_button("회원 목록 (납부율·참석율 포함)", excel.export_members_bytes(conn, year), f"회원목록_{year}.xlsx", XLSX)
        st.caption("내려받은 회원 파일은 그대로 다시 업로드할 수 있습니다. 납부액·납부율·참석율 열은 업로드 시 무시됩니다.")
        st.download_button("수입·지출 내역", excel.export_ledger_bytes(conn, year), f"수입지출내역_{year}.xlsx", XLSX)
        st.download_button("일정 및 출석 기록", excel.export_schedule_bytes(conn, year), f"일정_출석_{year}.xlsx", XLSX)
