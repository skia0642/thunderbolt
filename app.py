import altair  # noqa: F401  화면 첫 표시가 느려지지 않도록 무거운 모듈을 미리 불러온다
import pandas  # noqa: F401
import streamlit as st

from db.connection import ensure_db
from services.settings import as_of, list_years
from theme import inject_css

st.set_page_config(page_title="야구 동호회 회원관리", page_icon="⚾", layout="wide")

_conn = ensure_db()
_years = list_years(_conn)
_today = as_of(_conn).isoformat()
_conn.close()
inject_css()

# 새 연도를 만든 직후에는 그 연도를 바로 보여준다 (위젯이 만들어지기 전에만 값을 바꿀 수 있다).
if "_next_view_year" in st.session_state:
    st.session_state["view_year"] = st.session_state.pop("_next_view_year")
if st.session_state.get("view_year") not in _years:
    st.session_state["view_year"] = _years[0]

navigation = st.navigation([
    st.Page("pages/dashboard.py", title="대시보드", icon="📊", default=True),
    st.Page("pages/members.py", title="회원", icon="👥"),
    st.Page("pages/finance.py", title="회비", icon="💰"),
    st.Page("pages/schedule.py", title="일정", icon="📅"),
    st.Page("pages/excel.py", title="엑셀", icon="📁"),
    st.Page("pages/settings.py", title="설정", icon="⚙️"),
])
with st.sidebar:
    st.markdown('<div class="sidebar-brand">⚾ 동호회 회원관리</div>'
                f'<div class="sidebar-sub">회장단 전용 · 기준일 {_today}</div>', unsafe_allow_html=True)
    if len(_years) > 1:
        st.selectbox("조회 연도", _years, key="view_year",
                     help="지난 연도는 조회만 가능합니다. 입력·수정은 최신 연도에서 합니다.")
navigation.run()
