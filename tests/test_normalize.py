from app.parser.normalize import fold, fold_aligned


def test_fold_lowercases_strips_diacritics_and_collapses_spaces() -> None:
    assert fold("Xuất  Từ KHO Tổng") == "xuat tu kho tong"


def test_fold_turns_d_stroke_into_plain_d() -> None:
    assert fold("Đĩa") == "dia"


def test_fold_aligned_keeps_length_so_spans_map_back_to_original() -> None:
    assert fold_aligned("Đĩa  Tổng") == "dia  tong"
