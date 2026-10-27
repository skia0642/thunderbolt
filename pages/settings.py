from datetime import date

import streamlit as st

from db.connection import connect
from seed.seed_data import seed
from services.errors import ValidationError
from services.settings import get_settings, set_as_of_today, update_settings
from ui_utils import flash, money_input, page_header, show_flash

page_header("설정", "연도별 기본값과 기준일, 샘플 데이터를 관리합니다.")
show_flash()

with connect() as conn:
    s = get_settings(conn)
    st.subheader(f"{s['year']}년 기본값")
    with st.form("settings"):
        c1, c2 = st.columns(2)
        carry = money_input("이월 잔액 (원)", s["carry_over"], c1)
        reserve = money_input("차년도 예비비 (원)", s["reserve"], c2)
        league = money_input("리그비 (원)", s["league_fee"], c1)
        dues = money_input("연 회비 (인당, 원)", s["annual_dues"], c2)
        venue = money_input("연습 대관료 (원)", s["venue_fee"], c1)
        games = c2.number_input("리그 경기 수", min_value=0, max_value=100, value=s["league_games"])
        as_of = c1.date_input("기준일 ('오늘'로 취급하는 날짜)", value=date.fromisoformat(s["as_of"]),
                              min_value=date(s["year"], 1, 1), max_value=date(s["year"], 12, 31),
                              help="잔여 일정, 연체 판정, 분납 기한 도래 여부가 이 날짜를 기준으로 계산됩니다.")
        save = st.form_submit_button("저장", type="primary")
    if st.button("기준일을 오늘 날짜로 맞추기", help="잔여 일정·연체 판정·분납 기한이 오늘 기준으로 계산됩니다."):
        try:
            flash(f"기준일을 {set_as_of_today(conn)}(오늘)로 맞췄습니다.")
            st.rerun()
        except ValidationError as e:
            for m in e.messages:
                st.error(m)
    if save:
        try:
            update_settings(conn, s["year"], {
                "carry_over": carry, "reserve": reserve, "league_fee": league, "annual_dues": dues,
                "venue_fee": venue, "league_games": games, "as_of": as_of})
            flash("설정을 저장했습니다. 이미 부과된 회원별 회비는 바뀌지 않고, 새로 등록하는 회원부터 새 금액이 적용됩니다.")
            st.rerun()
        except ValidationError as e:
            for m in e.messages:
                st.error(m)

    st.divider()
    with st.container(border=True):
        st.subheader("⚠️ 위험 구역 · 샘플 데이터 초기화")
        st.caption("모든 회원·납부·일정·내역이 지워지고 가상 데이터(회원 20명)로 다시 채워집니다. 되돌릴 수 없습니다.")
        if st.button("샘플 데이터 초기화"):
            st.session_state["confirm_reset"] = True
        if st.session_state.get("confirm_reset"):
            st.warning("정말 초기화할까요? 지금까지 입력한 데이터가 모두 사라집니다.")
            r1, r2, _ = st.columns([1, 1, 4])
            if r1.button("초기화 확인", type="primary"):
                seed(conn)
                st.session_state["confirm_reset"] = False
                flash("가상 데이터를 다시 생성했습니다.")
                st.rerun()
            if r2.button("취소"):
                st.session_state["confirm_reset"] = False
                st.rerun()
