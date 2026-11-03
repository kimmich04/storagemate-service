"""Sinh dữ liệu mẫu 1 tuần (26/10 – 01/11/2026) cho Eggyolk Coffee — Storagemate."""
import csv
import random
from datetime import date, datetime, timedelta

random.seed(42)

# ingredient_key: (tên trong tin nhắn, đơn vị code, đơn vị hiển thị, hệ số base, lô nhập, ngưỡng đặt hàng)
ITEMS = {
    "trung_ga":             ("trứng",                "vi",   "vỉ",   12, 30, 14),
    "cafe_robusta":         ("cafe robusta",         "bich", "bịch", 1,  5,  2),
    "cafe_arabica":         ("cafe arabica",         "bich", "bịch", 1,  4,  2),
    "sua_tuoi":             ("sữa tươi",             "hop",  "hộp",  1,  12, 4),
    "sua_beo":              ("sữa béo",              "hop",  "hộp",  1,  6,  2),
    "sua_dac":              ("sữa đặc",              "hop",  "hộp",  1,  12, 4),
    "matcha":               ("matcha",               "hop",  "hộp",  1,  3,  1),
    "rich":                 ("Rich",                 "hop",  "hộp",  1,  6,  2),
    "whipping_cream":       ("whipping cream",       "hop",  "hộp",  1,  6,  2),
    "bot_kem_cheese":       ("bột kem cheese",       "hop",  "hộp",  1,  4,  2),
    "croissant":            ("croissant",            "cai",  "cái",  1,  50, 12),
    "pain_au_chocolat":     ("pain au chocolat",     "cai",  "cái",  1,  30, 8),
    "timbering_trung_muoi": ("timbering trứng muối", "cai",  "cái",  1,  20, 5),
    "timbering_do_cream":   ("timbering đỏ cream",   "cai",  "cái",  1,  20, 5),
    "timbering_chocolate":  ("timbering chocolate",  "cai",  "cái",  1,  20, 5),
    "raisin":               ("raisin",               "cai",  "cái",  1,  20, 5),
}

# Lịch xuất: (giờ, item, (sl ngày thường, sl cuối tuần), chu kỳ ngày, lệch)
XUAT = [
    (7,  "trung_ga",             (7, 5), 1, 0),  # ngày thường xuất 1 lần, cuối tuần 2 lần
    (13, "trung_ga",             (0, 4), 1, 0),
    (7,  "cafe_robusta",         (2, 2), 2, 0),
    (7,  "cafe_arabica",         (1, 1), 2, 0),
    (7,  "sua_dac",              (2, 2), 1, 0),
    (7,  "sua_tuoi",             (2, 3), 1, 0),
    (9,  "sua_beo",              (1, 1), 2, 1),
    (9,  "matcha",               (1, 1), 3, 1),
    (9,  "rich",                 (1, 1), 2, 0),
    (9,  "whipping_cream",       (1, 1), 2, 1),
    (14, "bot_kem_cheese",       (1, 1), 2, 0),
    (8,  "croissant",            (8, 10), 1, 0),
    (8,  "pain_au_chocolat",     (5, 6), 1, 0),
    (8,  "timbering_trung_muoi", (4, 5), 2, 0),
    (8,  "timbering_do_cream",   (4, 5), 2, 1),
    (8,  "timbering_chocolate",  (4, 5), 2, 0),
    (8,  "raisin",               (4, 5), 2, 1),
]

START = date(2026, 10, 26)
DAYS = 7
STAFF = ["NV01", "NV02"]

stock = {k: 0 for k in ITEMS}
events = []  # (datetime, order, action, item, qty)


def need_today(item, day_idx, weekend):
    total = 0
    for h, it, (wd, we), cycle, off in XUAT:
        if it == item and (day_idx - off) % cycle == 0:
            total += we if weekend else wd
    return total


for d in range(DAYS):
    day = START + timedelta(days=d)
    weekend = day.weekday() >= 5
    # Nhập lúc 6h nếu tồn không đủ cho hôm nay hoặc dưới ngưỡng
    for item, (_, _, _, _, lot, reorder) in ITEMS.items():
        need = need_today(item, d, weekend)
        if stock[item] < max(reorder, need):
            qty = lot
            while stock[item] + qty < need:
                qty += lot
            stock[item] += qty
            events.append((datetime(day.year, day.month, day.day, 6), 0, "nhap", item, qty))
    # Xuất theo lịch
    for h, item, (wd, we), cycle, off in XUAT:
        if (d - off) % cycle != 0:
            continue
        qty = we if weekend else wd
        if qty == 0:
            continue
        stock[item] -= qty
        assert stock[item] >= 0, (day, item)
        events.append((datetime(day.year, day.month, day.day, h), 1, "xuat", item, qty))

events.sort(key=lambda e: (e[0], e[1], e[3]))

rows = []
for i, (dt, _, action, item, qty) in enumerate(events, start=1):
    name, unit, unit_vn, factor, _, _ = ITEMS[item]
    verb = "nhập" if action == "nhap" else "xuất"
    raw = f"{verb} {qty} {unit_vn} {name} {dt.day}/{dt.month} {dt.hour} giờ"
    # Ca sáng NV01, ca chiều NV02
    sender = STAFF[0] if dt.hour < 12 else STAFF[1]
    rows.append({
        "id": i,
        "raw_message": raw,
        "sender": sender,
        "action": action,
        "quantity": qty,
        "unit": unit,
        "ingredient": item,
        "event_time": dt.strftime("%Y-%m-%d %H:%M"),
        "base_quantity": qty * factor,
    })

with open("eggyolk_week_2026-10-26.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("rows:", len(rows))
print("nhap:", sum(r["action"] == "nhap" for r in rows), "xuat:", sum(r["action"] == "xuat" for r in rows))
print("ton cuoi tuan:", {k: v for k, v in stock.items()})
