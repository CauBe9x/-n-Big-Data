"""Các hàm làm sạch & chuẩn hoá dữ liệu VietJobs.

Dữ liệu gốc được trích xuất bằng LLM từ TopCV nên có nhiều dạng ghi khác nhau:
- Danh sách lưu dạng chuỗi Python: "['Excel', 'Word']"
- Địa điểm có thể là tỉnh, quận/huyện hoặc nhiều nơi: "hà nội, hồ chí minh", "cầu giấy", "biên hoà"
- Kinh nghiệm: "Không yêu cầu", "6 tháng", "1 năm", "Trên 5 năm", ...
- Lương: salary_min/salary_max (triệu VNĐ/tháng), 0 = thoả thuận.
"""
from __future__ import annotations

import ast
import math
import re
import unicodedata
from typing import Iterable

# ---------------------------------------------------------------------------
# Tiện ích chuỗi tiếng Việt
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """'Hồ Chí Minh' -> 'ho chi minh' (dùng làm khoá so khớp)."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d")


def ascii_key(text: str) -> str:
    text = strip_accents(text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "[]"}


def parse_list(value) -> list[str]:
    """Chuyển "['a', 'b']" hoặc "a, b" thành ['a', 'b']."""
    if is_missing(value):
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        items = None
        if text.startswith("["):
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, (list, tuple)):
                    items = list(parsed)
            except (ValueError, SyntaxError):
                items = None
            if items is None:
                text = text.strip("[]")
        if items is None:
            items = [p for p in re.split(r"[;,]", text)]
    out = []
    for it in items:
        if is_missing(it):
            continue
        s = re.sub(r"\s+", " ", str(it)).strip(" '\"\t\n-•*+")
        if s:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Địa điểm -> Tỉnh/Thành (theo 63 tỉnh thành trước sáp nhập, quen thuộc khi phân tích)
# ---------------------------------------------------------------------------

PROVINCES = [
    "Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "An Giang", "Bà Rịa - Vũng Tàu",
    "Bắc Giang", "Bắc Kạn", "Bạc Liêu", "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước",
    "Bình Thuận", "Cà Mau", "Cao Bằng", "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai", "Đồng Tháp",
    "Gia Lai", "Hà Giang", "Hà Nam", "Hà Tĩnh", "Hải Dương", "Hậu Giang", "Hòa Bình", "Hưng Yên",
    "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An",
    "Nam Định", "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên", "Quảng Bình", "Quảng Nam",
    "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình",
    "Thái Nguyên", "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang", "Vĩnh Long",
    "Vĩnh Phúc", "Yên Bái",
]

# Bí danh / quận / huyện / thành phố trực thuộc -> tỉnh
_ALIASES: dict[str, str] = {
    # TP.HCM
    "tp hcm": "Hồ Chí Minh", "hcm": "Hồ Chí Minh", "tphcm": "Hồ Chí Minh", "sai gon": "Hồ Chí Minh",
    "thanh pho ho chi minh": "Hồ Chí Minh", "tp ho chi minh": "Hồ Chí Minh", "thu duc": "Hồ Chí Minh",
    "binh thanh": "Hồ Chí Minh", "go vap": "Hồ Chí Minh", "tan binh": "Hồ Chí Minh", "tan phu": "Hồ Chí Minh",
    "phu nhuan": "Hồ Chí Minh", "binh tan": "Hồ Chí Minh", "binh chanh": "Hồ Chí Minh", "hoc mon": "Hồ Chí Minh",
    "cu chi": "Hồ Chí Minh", "nha be": "Hồ Chí Minh", "can gio": "Hồ Chí Minh",
    # Hà Nội
    "ha noi": "Hà Nội", "hn": "Hà Nội", "ba dinh": "Hà Nội", "hoan kiem": "Hà Nội", "hai ba trung": "Hà Nội",
    "dong da": "Hà Nội", "tay ho": "Hà Nội", "cau giay": "Hà Nội", "thanh xuan": "Hà Nội", "hoang mai": "Hà Nội",
    "long bien": "Hà Nội", "nam tu liem": "Hà Nội", "bac tu liem": "Hà Nội", "tu liem": "Hà Nội", "ha dong": "Hà Nội",
    "son tay": "Hà Nội", "dong anh": "Hà Nội", "gia lam": "Hà Nội", "thanh tri": "Hà Nội", "soc son": "Hà Nội",
    "me linh": "Hà Nội", "hoai duc": "Hà Nội", "dan phuong": "Hà Nội", "thach that": "Hà Nội", "quoc oai": "Hà Nội",
    "chuong my": "Hà Nội", "thuong tin": "Hà Nội", "phu xuyen": "Hà Nội", "ung hoa": "Hà Nội", "my duc": "Hà Nội",
    "ba vi": "Hà Nội", "phuc tho": "Hà Nội", "thanh oai": "Hà Nội",
    # Các thành phố / huyện hay gặp
    "thu dau mot": "Bình Dương", "di an": "Bình Dương", "thuan an": "Bình Dương", "ben cat": "Bình Dương",
    "tan uyen": "Bình Dương", "bau bang": "Bình Dương", "bien hoa": "Đồng Nai", "long thanh": "Đồng Nai",
    "nhon trach": "Đồng Nai", "trang bom": "Đồng Nai", "vung tau": "Bà Rịa - Vũng Tàu", "ba ria": "Bà Rịa - Vũng Tàu",
    "chau duc": "Bà Rịa - Vũng Tàu", "phu my": "Bà Rịa - Vũng Tàu", "ba ria vung tau": "Bà Rịa - Vũng Tàu",
    "trang bang": "Tây Ninh", "long xuyen": "An Giang", "chau doc": "An Giang", "vinh": "Nghệ An", "tp vinh": "Nghệ An",
    "nha trang": "Khánh Hòa", "cam ranh": "Khánh Hòa", "da lat": "Lâm Đồng", "bao loc": "Lâm Đồng",
    "buon ma thuot": "Đắk Lắk", "dak lak": "Đắk Lắk", "dac lac": "Đắk Lắk", "dak nong": "Đắk Nông",
    "quy nhon": "Bình Định", "ha long": "Quảng Ninh", "mong cai": "Quảng Ninh", "cam pha": "Quảng Ninh",
    "uong bi": "Quảng Ninh", "viet tri": "Phú Thọ", "hue": "Thừa Thiên Huế", "thua thien hue": "Thừa Thiên Huế",
    "bim son": "Thanh Hóa", "sam son": "Thanh Hóa", "tu son": "Bắc Ninh", "que vo": "Bắc Ninh", "pho yen": "Thái Nguyên",
    "my tho": "Tiền Giang", "rach gia": "Kiên Giang", "phu quoc": "Kiên Giang", "cam giang": "Hải Dương",
    "chi linh": "Hải Dương", "tan an": "Long An", "duc hoa": "Long An", "ben luc": "Long An", "can giuoc": "Long An",
    "hoi an": "Quảng Nam", "tam ky": "Quảng Nam", "pleiku": "Gia Lai", "phan thiet": "Bình Thuận",
    "phan rang": "Ninh Thuận", "tuy hoa": "Phú Yên", "dong hoi": "Quảng Bình", "dong ha": "Quảng Trị",
    "vinh yen": "Vĩnh Phúc", "phuc yen": "Vĩnh Phúc", "ninh kieu": "Cần Thơ", "thai binh": "Thái Bình",
    "my hao": "Hưng Yên", "van lam": "Hưng Yên", "yen phong": "Bắc Ninh", "dong xoai": "Bình Phước",
    "hai chau": "Đà Nẵng", "son tra": "Đà Nẵng", "lien chieu": "Đà Nẵng", "ngu hanh son": "Đà Nẵng",
    "cam le": "Đà Nẵng", "thanh khe": "Đà Nẵng", "hoa vang": "Đà Nẵng", "hai an": "Hải Phòng",
    "le chan": "Hải Phòng", "ngo quyen": "Hải Phòng", "thuy nguyen": "Hải Phòng", "an duong": "Hải Phòng",
    "hong bang": "Hải Phòng", "do son": "Hải Phòng", "cat hai": "Hải Phòng",
    # bổ sung sau khi khảo sát dữ liệu thật
    "long khanh": "Đồng Nai", "phu ly": "Hà Nam", "duy tien": "Hà Nam", "dien ban": "Quảng Nam",
    "nui thanh": "Quảng Nam", "thang binh": "Quảng Nam", "dong giang": "Quảng Nam", "duy xuyen": "Quảng Nam",
    "yen my": "Hưng Yên", "van giang": "Hưng Yên", "an thi": "Hưng Yên", "dac nong": "Đắk Nông",
    "don duong": "Lâm Đồng", "duc trong": "Lâm Đồng", "lam ha": "Lâm Đồng", "binh xuyen": "Vĩnh Phúc",
    "tam dao": "Vĩnh Phúc", "cai rang": "Cần Thơ", "ngoc lac": "Thanh Hóa", "song cong": "Thái Nguyên",
    "sa pa": "Lào Cai", "sapa": "Lào Cai", "bac ha": "Lào Cai", "tien lang": "Hải Phòng", "dong trieu": "Quảng Ninh",
    "nghi loc": "Nghệ An", "hung nguyen": "Nghệ An", "nghia dan": "Nghệ An", "tam diep": "Ninh Bình",
    "cu kuin": "Đắk Lắk", "cho gao": "Tiền Giang", "dien khanh": "Khánh Hòa", "huong tra": "Thừa Thiên Huế",
    "phu loc": "Thừa Thiên Huế", "an khe": "Gia Lai", "sa dec": "Đồng Tháp", "tien du": "Bắc Ninh",
    "dong hung": "Thái Bình", "tay hoa": "Phú Yên", "ha dong": "Hà Nội", "hoa lac": "Hà Nội",
}
for _p in PROVINCES:
    _ALIASES.setdefault(ascii_key(_p), _p)
_ALIASES["thanh hoa"] = "Thanh Hóa"
_ALIASES["khanh hoa"] = "Khánh Hòa"
_ALIASES["hoa binh"] = "Hòa Bình"
for _i in range(1, 13):
    _ALIASES[f"quan {_i}"] = "Hồ Chí Minh"
    _ALIASES[f"q{_i}"] = "Hồ Chí Minh"

_NORTH = {"Hà Nội", "Hải Phòng", "Bắc Giang", "Bắc Kạn", "Bắc Ninh", "Cao Bằng", "Điện Biên", "Hà Giang", "Hà Nam",
          "Hải Dương", "Hòa Bình", "Hưng Yên", "Lai Châu", "Lạng Sơn", "Lào Cai", "Nam Định", "Ninh Bình", "Phú Thọ",
          "Quảng Ninh", "Sơn La", "Thái Bình", "Thái Nguyên", "Tuyên Quang", "Vĩnh Phúc", "Yên Bái"}
_CENTRAL = {"Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình", "Quảng Trị", "Thừa Thiên Huế", "Đà Nẵng", "Quảng Nam",
            "Quảng Ngãi", "Bình Định", "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Bình Thuận", "Kon Tum", "Gia Lai",
            "Đắk Lắk", "Đắk Nông", "Lâm Đồng"}


def province_region(name: str) -> str:
    """Miền của tỉnh/thành (phục vụ dashboard)."""
    if name in _NORTH:
        return "Miền Bắc"
    if name in _CENTRAL:
        return "Miền Trung"
    if name in PROVINCES:
        return "Miền Nam"
    return "Khác"


_PREFIX_RE = re.compile(r"^(thanh pho|tp|tinh|quan|huyen|thi xa|tx|thi tran|phuong|xa)\s+")


def _match_province(part: str) -> str | None:
    key = ascii_key(part)
    if not key:
        return None
    if key in _ALIASES:
        return _ALIASES[key]
    stripped = _PREFIX_RE.sub("", key)
    if stripped in _ALIASES:
        return _ALIASES[stripped]
    # "huyện dakchung, tỉnh sekong" -> thử từng cụm từ dài nhất có trong bảng
    for alias in sorted(_ALIASES, key=len, reverse=True):
        if len(alias) >= 4 and re.search(rf"\b{re.escape(alias)}\b", key):
            return _ALIASES[alias]
    return None


def normalize_location(location, country=None) -> tuple[str, list[str]]:
    """Trả về (tỉnh chính, danh sách tất cả tỉnh xuất hiện).

    Tin ở nước ngoài -> ('Nước ngoài', [...]); không xác định -> ('Khác', []).
    """
    if not is_missing(country) and ascii_key(str(country)) not in {"viet nam", "vietnam", "vn"}:
        return "Nước ngoài", []
    if is_missing(location):
        return "Khác", []
    found: list[str] = []
    parts = re.split(r"[,;/&|]| - |\bvà\b", str(location))
    i = 0
    while i < len(parts):
        part = parts[i]
        prov = _match_province(part)
        if prov is None and i + 1 < len(parts):  # "huyện X, tỉnh Y"
            prov = _match_province(parts[i + 1])
            if prov is not None:
                i += 1
        if prov and prov not in found:
            found.append(prov)
        i += 1
    return (found[0] if found else "Khác"), found


# ---------------------------------------------------------------------------
# Kinh nghiệm
# ---------------------------------------------------------------------------

def parse_experience(value) -> float | None:
    """'Không yêu cầu'->0, '6 tháng'->0.5, '2 năm'->2, 'Trên 5 năm'->6, 'Dưới 1 năm'->0.5."""
    if is_missing(value):
        return None
    text = strip_accents(str(value))
    if "khong" in text or "chua" in text or "no " in text:
        return 0.0
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", text)]
    if not nums:
        return None
    unit_month = "thang" in text or "month" in text
    val = sum(nums[:2]) / len(nums[:2])
    if unit_month:
        val = val / 12
    if "duoi" in text or "under" in text or "<" in text:
        val = val / 2
    elif "tren" in text or "hon" in text or "over" in text or ">" in text or "+" in text:
        val = val + 1
    return round(min(val, 30.0), 2)


def experience_bucket(years: float | None) -> str:
    if years is None:
        return "Không rõ"
    if years == 0:
        return "Không yêu cầu"
    if years < 1:
        return "Dưới 1 năm"
    if years <= 2:
        return "1-2 năm"
    if years <= 5:
        return "3-5 năm"
    return "Trên 5 năm"


EXPERIENCE_BUCKETS = ["Không yêu cầu", "Dưới 1 năm", "1-2 năm", "3-5 năm", "Trên 5 năm", "Không rõ"]


# ---------------------------------------------------------------------------
# Lương (đơn vị: triệu VNĐ / tháng)
# ---------------------------------------------------------------------------

def _to_float(value) -> float | None:
    if is_missing(value):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def parse_salary(salary_min, salary_max, salary_avg=None) -> tuple[float | None, float | None, float | None]:
    """Trả về (min, max, avg); None nếu thoả thuận."""
    lo = _to_float(salary_min) or 0.0
    hi = _to_float(salary_max) or 0.0
    if lo > 0 or hi > 0:
        if lo <= 0:
            lo = hi
        if hi <= 0:
            hi = lo
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi, round((lo + hi) / 2, 2)
    if not is_missing(salary_avg):
        m = re.search(r"\d+(?:[.,]\d+)?", str(salary_avg))
        if m:
            v = float(m.group().replace(",", "."))
            if v > 0:
                return v, v, v
    return None, None, None


# ---------------------------------------------------------------------------
# Kỹ năng
# ---------------------------------------------------------------------------

_SKILL_PREFIX = re.compile(
    r"^(co |có )?(kỹ năng|kĩ năng|ky nang|khả năng|kha nang|thành thạo|thanh thao|sử dụng thành thạo|"
    r"sử dụng tốt|sử dụng|biết sử dụng|kiến thức về|kiến thức|hiểu biết về|hiểu biết|am hiểu về|am hiểu|"
    r"có kinh nghiệm|kinh nghiệm|tốt|giỏi)\s+",
    flags=re.IGNORECASE,
)

# Gom các cách viết khác nhau về một tên chuẩn (khoá: ascii_key)
_SKILL_ALIASES = {
    "ms excel": "excel", "microsoft excel": "excel", "excel nang cao": "excel",
    "ms word": "word", "microsoft word": "word",
    "ms powerpoint": "powerpoint", "power point": "powerpoint", "ppt": "powerpoint",
    "ms office": "tin học văn phòng", "microsoft office": "tin học văn phòng", "office": "tin học văn phòng",
    "tin hoc van phong": "tin học văn phòng", "vi tinh van phong": "tin học văn phòng", "office 365": "tin học văn phòng",
    "word excel": "tin học văn phòng", "word excel powerpoint": "tin học văn phòng",
    "auto cad": "autocad", "cad": "autocad", "reactjs": "react", "react js": "react", "nodejs": "node.js",
    "node js": "node.js", "vuejs": "vue.js", "vue js": "vue.js", "js": "javascript", "ts": "typescript",
    "giao tiep": "giao tiếp", "giao tiep tot": "giao tiếp", "lam viec nhom": "làm việc nhóm",
    "teamwork": "làm việc nhóm", "lam viec doc lap": "làm việc độc lập", "thuyet trinh": "thuyết trình",
    "dam phan": "đàm phán", "quan ly thoi gian": "quản lý thời gian", "giai quyet van de": "giải quyết vấn đề",
    "chiu duoc ap luc cong viec": "chịu áp lực công việc", "chiu ap luc cong viec": "chịu áp lực công việc",
    "chiu duoc ap luc": "chịu áp lực công việc", "chiu ap luc": "chịu áp lực công việc",
    "chiu duoc ap luc cong viec cao": "chịu áp lực công việc", "trung thuc": "trung thực",
    "can than": "cẩn thận", "tu mi": "tỉ mỉ", "nhiet tinh": "nhiệt tình", "chu dong": "chủ động",
    "co tinh than trach nhiem": "tinh thần trách nhiệm", "tinh than trach nhiem": "tinh thần trách nhiệm",
    "tinh than trach nhiem cao": "tinh thần trách nhiệm", "trach nhiem": "tinh thần trách nhiệm",
    "co tinh than trach nhiem cao": "tinh thần trách nhiệm", "lanh dao": "lãnh đạo",
    "quan ly doi nhom": "quản lý đội nhóm", "to chuc": "tổ chức", "lap ke hoach": "lập kế hoạch",
    "phan tich": "phân tích", "tieng anh": "tiếng anh", "english": "tiếng anh",
}


_SKILL_ALIASES.update({
    "adobe photoshop": "photoshop", "adobe illustrator": "illustrator", "ai illustrator": "illustrator",
    "adobe premiere": "premiere", "premiere pro": "premiere", "adobe premiere pro": "premiere",
    "after effect": "after effects", "adobe after effects": "after effects", "ae": "after effects",
    "adobe indesign": "indesign", "google sheet": "google sheets", "google sheets": "google sheets",
    "phan mem ke toan misa": "misa", "phan mem misa": "misa", "cac phan mem ke toan": "phần mềm kế toán",
    "doc hieu ban ve ky thuat": "đọc bản vẽ kỹ thuật", "doc va hieu ban ve ky thuat": "đọc bản vẽ kỹ thuật",
    "doc ban ve ky thuat": "đọc bản vẽ kỹ thuật", "doc hieu ban ve": "đọc bản vẽ kỹ thuật",
    "doc ban ve": "đọc bản vẽ kỹ thuật", "lam viec theo nhom": "làm việc nhóm",
    "co trach nhiem": "tinh thần trách nhiệm", "co trach nhiem trong cong viec": "tinh thần trách nhiệm",
    "co trach nhiem voi cong viec": "tinh thần trách nhiệm", "trach nhiem trong cong viec": "tinh thần trách nhiệm",
    "chu dong trong cong viec": "chủ động", "chiu ap luc cao": "chịu áp lực công việc",
    "chiu duoc ap luc cao": "chịu áp lực công việc", "chiu duoc ap luc cong viec tot": "chịu áp lực công việc",
    "co tinh than cau tien": "cầu tiến", "tinh than cau tien": "cầu tiến", "co tinh than hoc hoi": "ham học hỏi",
    "tinh than hoc hoi": "ham học hỏi", "giao tiep hieu qua": "giao tiếp", "xu ly tinh huong linh hoat": "xử lý tình huống",
    "tu duy sang tao": "sáng tạo", "to chuc cong viec": "tổ chức", "thuong luong": "đàm phán",
    "microsoft office word excel powerpoint": "tin học văn phòng", "google ads adwords": "google ads",
    "facebook ads": "facebook ads", "fb ads": "facebook ads", "tiktok ads": "tiktok ads", "ms project": "ms project",
    "phan mem ke toan": "phần mềm kế toán", "excel word": "tin học văn phòng", "word excel ppt": "tin học văn phòng",
    "3d max": "3ds max", "3dsmax": "3ds max", "sketch up": "sketchup", "revit architecture": "revit",
    "nhanh nhen": "nhanh nhẹn", "cham chi": "chăm chỉ", "sieng nang": "chăm chỉ", "ham hoc hoi": "ham học hỏi",
})


def normalize_skill(skill: str) -> str | None:
    s = re.sub(r"\s+", " ", str(skill)).strip(" .;:-•*'\"").lower()
    for _ in range(2):
        s = _SKILL_PREFIX.sub("", s).strip()
    s = re.sub(r"\s+(tốt|cơ bản|nâng cao|hiệu quả)$", "", s).strip()
    if "(" in s:  # "tin học văn phòng (word, excel)" -> "tin học văn phòng"
        head = s.split("(", 1)[0].strip(" -:")
        if len(head) >= 2:
            s = head
    if len(s) < 2 or len(s) > 60:
        return None
    key = ascii_key(s)
    if not key or key in {"unk", "khac", "none", "n a"}:
        return None
    return _SKILL_ALIASES.get(key, s)


def normalize_skills(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        n = normalize_skill(v)
        if n and n not in seen:
            seen.append(n)
    return seen


# ---------------------------------------------------------------------------
# Ngành nghề
# ---------------------------------------------------------------------------

def category_display_name(slug) -> str:
    """'nông_nghiệp_năng_lượng_môi_trường' -> 'Nông nghiệp năng lượng môi trường'."""
    if is_missing(slug):
        return "Chưa phân loại"
    text = str(slug).replace("_", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:1].upper() + text[1:]


def parse_languages(value) -> list[str]:
    langs = []
    for part in parse_list(value):
        for p in re.split(r"[,/]", part):
            p = p.strip().lower()
            if p and p not in langs and p not in {"unk", "không", "none"}:
                langs.append(p)
    return langs
