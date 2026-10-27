"""화면 공통 서식. 금액·건수는 세 자리마다 쉼표를 붙이고, 숫자 정렬은 유지한다."""
import calendar as _calendar
import html

import altair as alt
import pandas as pd
import streamlit as st

from services.settings import list_years
from theme import BADGES, EXPENSE, INCOME, badge_css


def won(v) -> str:
    return f"{v:,}원"


def comma_style(df: pd.DataFrame, columns: dict[str, int] | None = None, badges: list[str] | None = None):
    """{열 이름: 소수 자릿수}로 지정한 숫자 열에 쉼표를 붙인 Styler를 돌려준다. 값이 없으면 '-'.

    badges에 열 이름을 주면 그 열의 상태 값(완납·예정·경기 등)에 색 배지 스타일을 입힌다.
    """
    styler = df.style.format({c: f"{{:,.{d}f}}" for c, d in (columns or {}).items()}, na_rep="-")
    for col in badges or []:
        if col in df.columns:
            styler = styler.map(badge_css, subset=[col])
    return styler


def page_header(title: str, caption: str = "") -> None:
    st.title(title)
    if caption:
        st.markdown(f'<div class="page-caption">{caption}</div>', unsafe_allow_html=True)


def monthly_chart(monthly: pd.DataFrame):
    """월별 수입·지출 막대 차트. monthly: 인덱스가 '1월'~'12월', 열이 수입·지출."""
    long = monthly.reset_index().melt(id_vars="월", var_name="구분", value_name="금액")
    return alt.Chart(long).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("월:N", sort=list(monthly.index), axis=alt.Axis(labelAngle=0, title=None)),
        xOffset="구분:N",
        y=alt.Y("금액:Q", axis=alt.Axis(format=",.0f", title="금액(원)")),
        color=alt.Color("구분:N", scale=alt.Scale(domain=["수입", "지출"], range=[INCOME, EXPENSE]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["월", "구분", alt.Tooltip("금액:Q", format=",.0f")],
    ).properties(height=300)


def flash(message: str, kind: str = "success") -> None:
    """다음 렌더링에서 보여줄 메시지를 쌓는다. 쓰고 나서 st.rerun()을 부르면 맨 위에 표시된다."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def money_input(label: str, value: int | None = 0, container=None, **kwargs) -> str:
    """금액 입력칸. 세 자리마다 쉼표로 보여주고, 입력값에서 쉼표·'원'을 뺀 문자열을 돌려준다.

    숫자가 아니면 문자열 그대로 서비스에 넘겨 '정수여야 합니다' 오류로 안내한다.
    """
    box = container or st
    raw = box.text_input(label, value="" if value is None else f"{value:,}", **kwargs)
    return raw.replace(",", "").replace("원", "").strip()


def view_year(conn) -> tuple[int, bool]:
    """사이드바에서 고른 조회 연도와 읽기 전용 여부(최신 연도가 아니면 True)."""
    years = list_years(conn)
    chosen = st.session_state.get("view_year")
    year = chosen if chosen in years else years[0]
    return year, year != years[0]


def readonly_notice(year: int) -> None:
    st.info(f"{year}년은 지난 연도라 조회만 가능합니다. 입력·수정은 사이드바에서 최신 연도로 바꾼 뒤 이용하세요.")


def calendar_html(rows: list[dict], year: int, month: int) -> str:
    """월간 달력 HTML. 사용자 입력(상대팀·장소)은 모두 이스케이프한다."""
    by_day: dict[int, list[dict]] = {}
    for r in rows:
        y, m, d = (int(x) for x in r["date"].split("-"))
        if (y, m) == (year, month):
            by_day.setdefault(d, []).append(r)
    head = "".join(f"<th>{d}</th>" for d in ("일", "월", "화", "수", "목", "금", "토"))
    body = []
    for week in _calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        cells = []
        for day in week:
            if day == 0:
                cells.append('<td class="cal-empty"></td>')
                continue
            items = []
            for r in by_day.get(day, []):
                fg, bg = BADGES.get(r["kind"], ("#333", "#eee"))
                label = html.escape(" ".join(x for x in (r.get("time"), r.get("opponent") or r.get("place")) if x))
                cancelled = " cal-cancel" if r["status"] == "취소" else ""
                state = "" if r["status"] == "예정" else f' <span class="cal-state">{html.escape(r["status"])}</span>'
                items.append(f'<div class="cal-item{cancelled}" title="{html.escape(r["kind"] + " " + label, quote=True)}" '
                             f'style="color:{fg};background:{bg}">'
                             f'<b>{html.escape(r["kind"])}</b> {label}{state}</div>')
            cells.append(f'<td><div class="cal-day">{day}</div>{"".join(items)}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="cal"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
