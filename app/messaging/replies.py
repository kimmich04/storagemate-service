"""Mọi câu bot trả lời (tiếng Việt) + cách trình bày bản tóm tắt phiếu."""

from datetime import date, datetime
from decimal import Decimal

from app.channels.base import Reply
from app.config import settings
from app.inventory.ledger import LedgerResult
from app.parser.catalog import ResolvedLine
from app.parser.normalize import fold
from app.parser.regex import UNKNOWN_LOC, Phieu, RawLine

MENU_OPTIONS = ["Mẫu Xuất", "Mẫu Nhập", "Hướng dẫn"]
LINE_HINT = "Tên hàng: số lượng"


def menu() -> Reply:
    return Reply("👋 Mình là bot ghi phiếu nhập/xuất kho.", quick_replies=MENU_OPTIONS)


def template_out(today: datetime) -> list[Reply]:
    return _template("Xuất", f"ngày {today:%d/%m} xuất từ kho tổng sang kho 220")


def template_in(today: datetime) -> list[Reply]:
    return _template("Nhập", f"ngày {today:%d/%m} nhập hàng về kho tổng")


def help_text() -> Reply:
    text = (
        "📖 Cách gửi phiếu\n"
        "Dòng 1: ngày + nhập/xuất + từ kho nào sang kho nào\n"
        f"Các dòng sau: mỗi món một dòng, ví dụ `{LINE_HINT}`\n"
        "• Viên nén caramel: 24\n"
        "• 2 thùng cafe trứng hoà tan\n"
        "• Unity trứng 15 hộp\n"
        "Bot đọc xong sẽ gửi lại bản tóm tắt để bạn kiểm tra."
    )
    return Reply(text, quick_replies=MENU_OPTIONS)


def unknown() -> Reply:
    text = (
        "🤔 Mình chưa hiểu tin này. Muốn ghi phiếu thì dòng đầu cần có ngày và chữ nhập/xuất, "
        "ví dụ: ngày 03/11 xuất từ kho tổng sang kho 220."
    )
    return Reply(text, quick_replies=MENU_OPTIONS)


def text_only() -> Reply:
    return Reply("Mình chỉ đọc được tin nhắn chữ. Bạn gõ phiếu giúp mình, hoặc gõ `menu` để xem mẫu nhé.")


def photo_only() -> Reply:
    return Reply(
        "📷 Đã nhận ảnh, nhưng mình chưa đọc được chữ trong ảnh. "
        "Bạn gõ phiếu vào phần chú thích của ảnh hoặc gửi tin chữ giúp mình nhé."
    )


def photo_received() -> Reply:
    return Reply("📷 Đã nhận ảnh")


def summary(phieu: Phieu, lines: list[ResolvedLine]) -> Reply:
    parts = [_heading(phieu), _date_line(phieu)]
    parts += [_line_text(number, line) for number, line in enumerate(lines, start=1)]
    parts += [f"⚠️ Chưa đọc được: «{raw}» → viết theo mẫu `{LINE_HINT}`" for raw in phieu.bad_lines]
    if not lines and not phieu.bad_lines:
        parts.append(f"⚠️ Chưa có dòng hàng nào — thêm mỗi món một dòng `{LINE_HINT}`")
    if any(line.status != "ok" for line in lines):
        parts.append(
            "👉 Sửa dòng có ❓ cho rõ tên/loại hàng (vd: Unity trứng 15 thùng) — dòng đó chưa được ghi."
        )
    return Reply("\n".join(parts))


def llm_confirm(phieu: Phieu, lines: list[ResolvedLine]) -> Reply:
    """Phiếu do LLM đọc: tóm tắt + hỏi OK/Sai. Chưa ghi gì cho tới khi nhân viên trả OK."""
    ask = (
        "🤖 Tin này không theo mẫu phiếu nên mình tự đọc, bạn kiểm tra giúp nhé.\n"
        f"Gõ OK để ghi sổ, Sai để hủy (trong {settings.PENDING_TTL_MINUTES} phút)."
    )
    return Reply(f"{summary(phieu, lines).text}\n\n{ask}")


def pending_rejected() -> Reply:
    return Reply("Đã hủy, chưa ghi gì. Bạn gõ lại giúp mình (hoặc gõ `menu` để xem mẫu phiếu) nhé.")


def pending_expired() -> Reply:
    return Reply("⌛ Bản chờ đã hết hạn nên chưa ghi gì. Bạn gửi lại tin giúp mình nhé.")


def nothing_pending() -> Reply:
    return Reply("Hiện không có phiếu nào đang chờ xác nhận. Gõ `menu` để xem mẫu phiếu nhé.")


def ledger_result(phieu: Phieu, result: LedgerResult) -> Reply | None:
    """Báo phần nào đã vào sổ và phần nào CHƯA, để nhân viên gõ lại đúng các dòng thiếu."""
    if result.date_error:
        return Reply(
            f"⚠️ Chưa ghi phiếu: {result.date_error}. Kiểm tra lại ngày ở dòng đầu rồi gửi lại cả phiếu.",
            parse_mode=None,
        )
    if result.total == 0:
        return None
    parts = []
    if result.written:
        parts.append(f"✅ Đã ghi {result.written}/{result.total} dòng — {_route(phieu)}, {phieu.date:%d/%m}.")
    if result.skipped:
        parts.append(f"⚠️ Chưa ghi {len(result.skipped)} dòng (CHƯA có trong sổ và dashboard):")
        parts += [f"• «{skip.raw}» — {skip.reason}" for skip in result.skipped]
        action = "xuất" if phieu.action == "OUT" else "nhập"
        parts.append(f"Gõ lại các dòng này thành phiếu mới, dòng đầu vẫn ghi ngày + {action} như phiếu cũ.")
    return Reply("\n".join(parts), parse_mode=None)


def invite_needed() -> Reply:
    return Reply(
        "🔒 Tài khoản Zalo này chưa được liên kết với nhân viên nào nên mình chưa ghi gì. "
        "Gửi mã mời 6 ký tự quản lý đưa cho bạn (vd: K7P2Q9) để bắt đầu nhé.",
        parse_mode=None,
    )


def invite_rejected() -> Reply:
    return Reply(
        "❌ Mã mời không đúng hoặc đã hết hạn. Kiểm tra lại mã, hoặc nhờ quản lý tạo mã mới cho bạn.",
        parse_mode=None,
    )


def welcome(staff_name: str, location_name: str) -> list[Reply]:
    greeting = Reply(f"Chào {staff_name} 👋 Bạn đã được kết nối với {location_name}.", parse_mode=None)
    return [greeting, help_text()]


def duplicate_question(group: tuple[int, ...], line: RawLine) -> Reply:
    numbers = [str(index + 1) for index in group]
    rows = ", ".join(numbers[:-1]) + f" và {numbers[-1]}"
    text = (
        f"❓ Dòng {rows} giống nhau.\n"
        f"A · Cùng loại → tổng {_qty(line.qty * len(group), line.unit)}\n"
        "B · Hai mẫu khác nhau → gõ lại phiếu, ghi rõ tên từng mẫu\n"
        f"C · Ghi trùng → chỉ tính {_qty(line.qty, line.unit)}\n"
        "Trả lời A, B hoặc C trong 10 phút."
    )
    return Reply(text)


def bot_error() -> Reply:
    return Reply("⚠️ Bot gặp lỗi, bạn gửi lại giúp mình nhé", parse_mode=None)


def resend_request() -> Reply:
    return Reply(
        "Bạn gõ lại phiếu giúp mình, ghi rõ tên từng mẫu cho khỏi trùng "
        "(ví dụ: khăn giấy egg yolk vuông: 2 · khăn giấy egg yolk dài: 2) nhé."
    )


def _template(kind: str, header: str) -> list[Reply]:
    lead = Reply(f"Mẫu phiếu {kind} 👇 Nhấn giữ tin dưới để sao chép, sửa tên hàng + số lượng rồi gửi lại.")
    return [lead, Reply(f"{header}\n{LINE_HINT}", parse_mode=None)]


def _heading(phieu: Phieu) -> str:
    return f"📦 {_route(phieu)}"


def _route(phieu: Phieu) -> str:
    if phieu.action == "IN":
        route = (
            f"về {phieu.to_loc}" if phieu.from_loc == UNKNOWN_LOC else f"{phieu.from_loc} → {phieu.to_loc}"
        )
        return f"NHẬP · {route}"
    return f"XUẤT · {phieu.from_loc} → {phieu.to_loc}"


def _date_line(phieu: Phieu) -> str:
    note = f"  ⚠️ {phieu.date_note}" if phieu.date_note else ""
    return f"📅 {_day(phieu.date)}{note}"


def _line_text(number: int, resolved: ResolvedLine) -> str:
    line = resolved.line
    name = resolved.item.name if resolved.item else line.name
    text = f"{number}. {name} — {_quantity(resolved)}"
    if resolved.status == "unknown":
        text += "  ❓ chưa có trong danh mục"
    elif resolved.status == "ambiguous":
        text += f"  ❓ {resolved.warning}"
    elif resolved.warning:
        text += f"  ⚠️ {resolved.warning}"
    if resolved.components:
        text += "\n   → " + " · ".join(f"{part} {_number(qty)}" for part, qty in resolved.components)
    return text


def _quantity(resolved: ResolvedLine) -> str:
    line = resolved.line
    if resolved.qty_base is None or resolved.base_unit is None:
        return _qty(line.qty, line.unit)
    base = _qty(resolved.qty_base, resolved.base_unit.lower())
    if line.unit and fold(line.unit) != fold(resolved.base_unit):
        return f"{_qty(line.qty, line.unit)} (= {base})"
    return base


def _qty(qty: Decimal, unit: str | None) -> str:
    return f"{_number(qty)} {unit}" if unit else _number(qty)


def _number(qty: Decimal) -> str:
    return f"{qty.normalize():f}".replace(".", ",")


def _day(value: date) -> str:
    return f"{value:%d/%m/%Y}"
