"""Kiểm thử các hàm làm sạch dữ liệu:  cd backend && pytest -q"""
from pipeline import cleaning as C


def test_parse_list():
    assert C.parse_list("['Excel', 'Word']") == ["Excel", "Word"]
    assert C.parse_list(None) == []
    assert C.parse_list("tiếng anh,tiếng nhật") == ["tiếng anh", "tiếng nhật"]


def test_location():
    assert C.normalize_location("hà nội, hồ chí minh", "Việt Nam") == ("Hà Nội", ["Hà Nội", "Hồ Chí Minh"])
    assert C.normalize_location("biên hoà", "Việt Nam")[0] == "Đồng Nai"
    assert C.normalize_location("cầu giấy", "Việt Nam")[0] == "Hà Nội"
    assert C.normalize_location("Quận 7, TP.HCM", "Việt Nam")[0] == "Hồ Chí Minh"
    assert C.normalize_location("huyện dakchung, tỉnh sekong", "Lào")[0] == "Nước ngoài"


def test_experience():
    assert C.parse_experience("Không yêu cầu") == 0
    assert C.parse_experience("6 tháng") == 0.5
    assert C.parse_experience("2 năm") == 2
    assert C.parse_experience("Trên 5 năm") == 6
    assert C.experience_bucket(2) == "1-2 năm"


def test_salary():
    assert C.parse_salary(15, 22, "18 triệu") == (15, 22, 18.5)
    assert C.parse_salary(0, 0, "Thoả thuận") == (None, None, None)
    assert C.parse_salary(0, 20, None) == (20, 20, 20)


def test_skills():
    assert C.normalize_skills(["Thành thạo MS Office", "Kỹ năng giao tiếp tốt", "ReactJS", "AutoCad"]) == \
        ["tin học văn phòng", "giao tiếp", "react", "autocad"]
