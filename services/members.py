"""회원 등록·수정·삭제와 입력 검증."""
import re
import sqlite3
from datetime import date

from services.errors import ValidationError
from services.payments import ensure_dues
from services.settings import get_settings

POSITIONS = ["투수", "포수", "1루수", "2루수", "3루수", "유격수", "내야수", "좌익수", "중견수", "우익수", "외야수"]
STATUSES = ("활동", "휴면")
PAY_TYPES = ("일괄", "분납")
MAX_NAME = 20


def normalize_phone(raw) -> str | None:
    """010-0000-0000 형식으로 맞춘다. 형식이 맞지 않으면 None."""
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 10 and digits.startswith("10"):  # 엑셀이 앞의 0을 지운 경우
        digits = "0" + digits
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return None


def parse_date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if hasattr(raw, "date") and not isinstance(raw, date):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def clean_member(conn, data: dict, exclude_id: int | None = None, check_duplicate: bool = True,
                 check_back: bool = True) -> dict:
    """입력값을 검증·정리한다. 오류가 하나라도 있으면 모아서 ValidationError."""
    errors = []
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("이름을 입력하세요.")
    elif len(name) > MAX_NAME:
        errors.append(f"이름은 {MAX_NAME}자 이하로 입력하세요.")

    phone = normalize_phone(data.get("phone"))
    if not str(data.get("phone") or "").strip():
        errors.append("연락처를 입력하세요.")
    elif phone is None:
        errors.append("연락처 형식이 올바르지 않습니다. (예: 010-1234-5678)")

    position = str(data.get("position") or "").strip() or None
    if position and len(position) > 10:
        errors.append("포지션은 10자 이하로 입력하세요.")

    back = data.get("back_number")
    if back in (None, ""):
        back = None
    else:
        try:
            if isinstance(back, float) and not back.is_integer():
                raise ValueError
            back = int(back)
            if not 0 <= back <= 99:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("등번호는 0~99 사이의 정수로 입력하세요.")
            back = None

    joined_raw = data.get("joined_at")
    joined = parse_date(joined_raw)
    if joined_raw not in (None, "") and joined is None:
        errors.append("가입일 형식이 올바르지 않습니다. (YYYY-MM-DD)")

    status = str(data.get("status") or "활동").strip()
    if status not in STATUSES:
        errors.append("상태는 활동 또는 휴면이어야 합니다.")
    pay_type = str(data.get("pay_type") or "일괄").strip()
    if pay_type not in PAY_TYPES:
        errors.append("납부방식은 일괄 또는 분납이어야 합니다.")

    if not errors:
        if check_duplicate and phone:
            dup = conn.execute(
                "SELECT id FROM member WHERE name = ? AND phone = ? AND id IS NOT ?", (name, phone, exclude_id)
            ).fetchone()
            if dup:
                errors.append("이름과 연락처가 같은 회원이 이미 있습니다.")
        if back is not None and check_back:
            dup = conn.execute(
                "SELECT name FROM member WHERE back_number = ? AND id IS NOT ?", (back, exclude_id)
            ).fetchone()
            if dup:
                errors.append(f"등번호 {back}번은 이미 {dup['name']} 회원이 사용 중입니다.")
    if errors:
        raise ValidationError(errors)
    return {
        "name": name, "phone": phone, "position": position, "back_number": back,
        "joined_at": joined.isoformat() if joined else None, "status": status, "pay_type": pay_type,
    }


def create_member(conn, data: dict) -> int:
    c = clean_member(conn, data)
    try:
        cur = conn.execute(
            "INSERT INTO member (name, phone, position, back_number, joined_at, status, pay_type) "
            "VALUES (:name, :phone, :position, :back_number, :joined_at, :status, :pay_type)", c,
        )
        ensure_dues(conn, cur.lastrowid, c["pay_type"])
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ValidationError("회원을 저장하지 못했습니다. 입력값을 확인하세요.") from e
    return cur.lastrowid


def update_member(conn, member_id: int, data: dict) -> None:
    old = conn.execute("SELECT * FROM member WHERE id = ?", (member_id,)).fetchone()
    if old is None:
        raise ValidationError("존재하지 않는 회원입니다.")
    c = clean_member(conn, data, exclude_id=member_id)
    year = get_settings(conn)["year"]
    if c["pay_type"] != old["pay_type"]:
        has_pay = conn.execute(
            "SELECT 1 FROM payment p JOIN dues d ON d.id = p.dues_id WHERE p.member_id = ? AND d.year = ?",
            (member_id, year),
        ).fetchone()
        if has_pay:
            raise ValidationError("이미 납부 내역이 있어 납부방식을 바꿀 수 없습니다. 납부를 취소한 뒤 변경하세요.")
    try:
        conn.execute(
            "UPDATE member SET name=:name, phone=:phone, position=:position, back_number=:back_number, "
            "joined_at=:joined_at, status=:status, pay_type=:pay_type WHERE id=:id", {**c, "id": member_id},
        )
        if c["pay_type"] != old["pay_type"]:
            conn.execute("DELETE FROM dues WHERE member_id = ? AND year = ?", (member_id, year))
        ensure_dues(conn, member_id, c["pay_type"])
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ValidationError("회원을 저장하지 못했습니다. 입력값을 확인하세요.") from e


def delete_member(conn, member_id: int) -> None:
    """회원과 납부·참석 기록을 삭제한다. 납부와 연동된 수입 거래도 함께 지운다."""
    if conn.execute("SELECT 1 FROM member WHERE id = ?", (member_id,)).fetchone() is None:
        raise ValidationError("존재하지 않는 회원입니다.")
    conn.execute(
        'DELETE FROM "transaction" WHERE id IN (SELECT transaction_id FROM payment WHERE member_id = ? AND transaction_id IS NOT NULL)',
        (member_id,),
    )
    conn.execute("DELETE FROM member WHERE id = ?", (member_id,))
    conn.commit()
