# Danh mục Eggyolk Coffee (catalog)

Nguồn: `../raw/eggyolk/` (dữ liệu 1 tuần + menu merch) và các quyết định khi brainstorm 2026-11-02.
Dùng cho: seed DB (`scripts/seed_items.py`), regex/validate, sinh synthetic NER.

| File | Nội dung |
|------|----------|
| `products.csv` | **File gốc để sửa tay.** 1 dòng / sản phẩm: tên, nhóm, đơn vị gốc, tên gọi khác (`\|`), màu, size, tồn tối thiểu |
| `colors.csv` | Màu + tên gọi khác (dùng chung cho mọi sản phẩm) |
| `items.csv` | **Sinh ra** — 1 dòng / biến thể (SKU) = sản phẩm × màu × size. Đây là thứ sổ cái ghi vào |
| `units.csv` | **Sinh ra** — quy đổi về đơn vị gốc |

Sửa `products.csv` → sinh lại `items.csv`, `units.csv` (`ml/scripts/build_catalog.py`, chưa viết; tạm thời sinh bằng script tay).

## Quy ước đã chốt
- Cú pháp: `[nhập|xuất] [số lượng] [đơn vị] [tên món] [màu] [size] [giờ] [ngày]`; món không có biến thể bỏ màu/size.
- 1 thùng = 30 hộp/bịch cho: nguyên liệu dạng hộp/bịch, cà phê sấy lạnh, hạt bán lẻ, viên nén. Ly/đĩa/áo không có thùng.
- Trứng: đơn vị gốc quả, 1 vỉ = 12 quả.
- Viên nén: 12 viên/hộp nhưng xuất nguyên hộp → đơn vị gốc **hộp**, chưa có đơn vị "viên".
- Set/box xuất nguyên bộ; "set sấy lạnh 3 vị" là 1 sản phẩm (đơn vị `set`).
- Hạt pha quầy (`cafe_robusta`, `cafe_arabica`) ≠ hạt bán lẻ (`hat_*`).
- Merch "xuất" = mang từ kho ra kệ trưng bày.
- Tên gọi khác khai báo theo phần (sản phẩm / màu / size), parser ghép lại; thiếu màu/size bắt buộc → bot hỏi lại.
- Thêm món mới qua Zalo: làm **sau** khi xong Zalo Bot.

## Do Claude tự đặt — cần bạn xem lại
- Tên chuẩn tiếng Việt cho merch (vd "ly 2 lớp" = Double Wall Cup) và toàn bộ cột `aliases`.
- Không gán alias trần `robusta`/`arabica` cho món nào → tin chỉ ghi "robusta" sẽ bị hỏi lại.
- Màu tiếng Việt từ menu tiếng Anh: Red Orange = đỏ cam, Blue = xanh dương, Cyan = xanh ngọc, Beige = be.
- `min_stock_base` nguyên liệu lấy từ ngưỡng đặt hàng trong `gen_eggyolk.py`; merch để trống.

## Còn thiếu
- Phin nhôm có 5 màu nhưng chưa biết màu nào → đang là 1 dòng không màu.
- Tồn tối thiểu cho merch / sấy lạnh / viên nén / hạt bán lẻ.
- `raw/eggyolk/eggyolk_week_2026-10-26.csv` dùng thứ tự ngày-trước-giờ (cũ) → đảo lại khi dùng làm template.
