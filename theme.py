"""화면 색상·CSS를 한곳에서 관리한다. 색을 바꾸려면 이 파일만 고친다."""
import streamlit as st

PRIMARY = "#1B3A5C"      # 네이비 (포인트)
INCOME = "#2F6DB5"       # 차트: 수입
EXPENSE = "#D9822B"      # 차트: 지출
MUTED = "#5F6B7A"
BORDER = "#DDE2E9"
SURFACE = "#F3F5F8"

# 상태 배지: 글자색, 배경색. 색만으로 구분하지 않도록 항상 텍스트와 함께 쓴다.
BADGES = {
    "완납": ("#1E7D4F", "#E4F4EA"), "분납중": ("#1F5FA8", "#E3EEFA"), "미납": ("#8A5A00", "#FFF1CC"),
    "연체": ("#B3261E", "#FDE7E5"), "면제": ("#5F6B7A", "#EDEFF2"),
    "예정": ("#1F5FA8", "#E3EEFA"), "완료": ("#1E7D4F", "#E4F4EA"), "취소": ("#5F6B7A", "#EDEFF2"),
    "경기": ("#7A2E8E", "#F3E6F8"), "연습": ("#0B6B6B", "#DDF2F2"),
    "수입": ("#1F5FA8", "#E3EEFA"), "지출": ("#9A4A00", "#FDEBD8"),
    "납부": ("#1E7D4F", "#E4F4EA"), "일정": ("#0B6B6B", "#DDF2F2"), "수동": ("#5F6B7A", "#EDEFF2"),
    "휴면": ("#5F6B7A", "#EDEFF2"),
    "참석": ("#1E7D4F", "#E4F4EA"), "결석": ("#B3261E", "#FDE7E5"),
    "신규": ("#1E7D4F", "#E4F4EA"), "갱신": ("#1F5FA8", "#E3EEFA"), "오류": ("#B3261E", "#FDE7E5"),
}

CSS = f"""
<style>
html, body, [class*="css"], .stApp {{
    font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px; }}
h1 {{ font-size: 1.9rem !important; font-weight: 700 !important; color: {PRIMARY}; letter-spacing: -0.02em; padding-bottom: .2rem; }}
h2, h3 {{ color: {PRIMARY}; letter-spacing: -0.01em; }}
h3 {{ font-size: 1.15rem !important; margin-top: .6rem; }}
.page-caption {{ color: {MUTED}; font-size: .92rem; margin: -.4rem 0 1.1rem 0; }}

/* 지표 카드 */
[data-testid="stMetric"] {{
    background: #fff; border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 18px;
    box-shadow: 0 1px 2px rgba(27,58,92,.05);
}}
[data-testid="stMetric"] {{ min-height: 118px; }}
.big-number {{ font-size: 1.6rem; font-weight: 700; color: {PRIMARY}; font-variant-numeric: tabular-nums; margin: .1rem 0 .5rem 0; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .86rem; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: {PRIMARY}; font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; }}

/* 탭 */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 14px; font-weight: 600; }}

/* 사이드바 */
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
.sidebar-brand {{ font-weight: 800; color: {PRIMARY}; font-size: 1.05rem; margin: .2rem 0 .1rem 0; }}
.sidebar-sub {{ color: {MUTED}; font-size: .8rem; }}

/* 카드(테두리 컨테이너) */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}

/* 일정 강조 */
.next-card {{ border-left: 5px solid {PRIMARY}; background: {SURFACE}; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; }}
.next-card .d {{ font-size: 1.25rem; font-weight: 800; color: {PRIMARY}; }}
.next-card .m {{ color: {MUTED}; font-size: .9rem; }}
.badge {{ display:inline-block; padding: 1px 9px; border-radius: 999px; font-size: .78rem; font-weight: 700; margin-right: 6px; }}

/* 월간 달력 */
table.cal {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
table.cal th {{ background: {SURFACE}; color: {MUTED}; font-size: .8rem; padding: 6px 0; border: 1px solid {BORDER}; }}
table.cal td {{ vertical-align: top; height: 92px; padding: 4px 6px; border: 1px solid {BORDER}; background: #fff; }}
table.cal td.cal-empty {{ background: {SURFACE}; }}
.cal-day {{ font-size: .8rem; color: {MUTED}; font-weight: 700; }}
.cal-item {{ font-size: .75rem; border-radius: 6px; padding: 2px 6px; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.cal-item.cal-cancel {{ text-decoration: line-through; opacity: .6; }}
.cal-state {{ font-size: .7rem; opacity: .8; }}

/* 업로드 단계 */
.steps {{ display:flex; gap: 10px; margin: .4rem 0 1rem 0; flex-wrap: wrap; }}
.step {{ flex: 1; min-width: 180px; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 14px; background:#fff; }}
.step b {{ color: {PRIMARY}; }}
.step.on {{ border-color: {PRIMARY}; background: #EEF3F9; }}
.step.done {{ border-color: #1E7D4F; background: #F0F9F3; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge_html(label: str) -> str:
    fg, bg = BADGES.get(label, (MUTED, SURFACE))
    return f'<span class="badge" style="color:{fg};background:{bg}">{label}</span>'


def badge_css(value) -> str:
    """Styler.map용: 배지 사전에 있는 값만 색을 입힌다."""
    colors = BADGES.get(value)
    if not colors:
        return ""
    return f"color: {colors[0]}; background-color: {colors[1]}; font-weight: 600"
