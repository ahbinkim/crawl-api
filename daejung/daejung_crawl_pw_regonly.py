# -*- coding: utf-8 -*-
"""
대정 검색 최소판 (HTTP-only, q= 고정)
- 검색: GET /02_product/search/?q=키워드
- 첫 행에서 code/price/stock/idx 추출
- 팝업: GET /02_product/search/popup/?idx=XXXX 로 labels 추출
- 출력: brand, code, price, discount_price(10%↓, 100원 반올림), stock_label, labels
"""

import urllib.request, urllib.parse, urllib.error
import re, json, html as htmllib
from decimal import Decimal, ROUND_HALF_UP

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
POPUP_PREFIX = f"{BASE}/02_product/search/popup/?idx="  # 예: ...?idx=6963

HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "close",
    "Referer": SEARCH_URL,
}

# tbody 내 첫 tr 기준으로 파싱 (0-based 인덱스)
TD_IDX = {"cas":1, "code":2, "name":3, "pack":5, "price":7, "stock":8}
RX_INT  = re.compile(r"(\d[\d,]*)")
RX_IDX  = re.compile(r"/popup/\?idx=([0-9]{4})")
KEEP_KEYS = (
    "기존물질","유해","유해화학물질","신규화학물질",
    "위험","규제","관계법령","산업안전보건법","화학물질","Remark"
)

def http_get(url: str, timeout=12) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None

def decode_html(raw: bytes | None) -> str:
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except Exception:
        pass
    try:
        return raw.decode("cp949")
    except Exception:
        return raw.decode("utf-8", "replace")

def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("\xa0", " ")
    return htmllib.unescape(s).strip()

def parse_int(s: str) -> int | None:
    m = RX_INT.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None

def discount_round(price: int | None, rate=0.10, unit=100) -> int | None:
    if price is None:
        return None
    val = Decimal(price) * Decimal(1 - rate)
    return int((val / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit)

def submit_search(q: str) -> str:
    url = SEARCH_URL + "?" + urllib.parse.urlencode({"q": q})
    return decode_html(http_get(url))

def parse_first_row(html: str) -> dict | None:
    # 첫 tbody > tr 하나만 추출
    m = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, flags=re.S|re.I)
    if not m:
        return None
    tbody = m.group(1)
    m2 = re.search(r"<tr[^>]*>(.*?)</tr>", tbody, flags=re.S|re.I)
    if not m2:
        return None
    row_html = m2.group(1)

    # 모든 td 파싱
    tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.S|re.I)
    if len(tds) <= TD_IDX["stock"]:
        return None

    code = strip_tags(tds[TD_IDX["code"]]) or None
    price = parse_int(strip_tags(tds[TD_IDX["price"]]))
    stock_label = strip_tags(tds[TD_IDX["stock"]])

    # idx (팝업 링크에서 추출)
    m_idx = RX_IDX.search(row_html)
    idx = m_idx.group(1) if m_idx else None

    return {
        "brand": "대정화금",
        "code": code,
        "price": price,
        "discount_price": discount_round(price, unit=100),
        "stock_label": stock_label,
        "idx": idx,
    }

def fetch_labels(idx: str) -> list[str]:
    html = decode_html(http_get(POPUP_PREFIX + idx))
    if not html:
        return []
    # 태그 제거 → 라인 분해
    text = strip_tags(html)
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    kept = [ln for ln in lines if any(k in ln for k in KEEP_KEYS)]
    # 중복 제거
    seen, out = set(), []
    for ln in kept:
        n = re.sub(r"\s+", " ", ln)
        if n not in seen:
            out.append(n); seen.add(n)
    return out

def search_minimal(q: str, first_only=True, include_labels=True):
    html = submit_search(q)
    row = parse_first_row(html)
    if not row:
        return []
    labels = []
    if include_labels and row.get("idx"):
        labels = fetch_labels(row["idx"])
    return [{
        "brand": row["brand"],
        "code": row["code"],
        "price": row["price"],
        "discount_price": row["discount_price"],
        "stock_label": row["stock_label"],
        "labels": labels,
    }]

if __name__ == "__main__":
    try:
        kw = input("🔎 대정 제품코드/키워드: ").strip()
    except EOFError:
        kw = ""
    data = search_minimal(kw or "에탄올", first_only=True, include_labels=True)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
