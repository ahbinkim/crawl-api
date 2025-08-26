# -*- coding: utf-8 -*-
"""
대정 최소 데이터 수집 (Playwright / 기존 정상작동 코드 기반)
- 검색/테이블 파싱은 기존 로직 유지
- 팝업: expect_popup 대신 idx 추출 후 직접 URL 접속
- 라벨: div.control_wrap2 p.pp 텍스트만 수집
"""

from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True
DEFAULT_TIMEOUT = 4000

# --- Launch args (변경점 반영) ---
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_rx_int = re.compile(r"(\d[\d,]*)")
_rx_idx = re.compile(r"/popup/\?idx=(\d{4})|idx\s*=\s*(\d{4})", re.I)

# ---- table indices (0-based) ----
TD_IDX = {
    "cas": 1,        # 1-based 2
    "code": 2,       # 1-based 3
    "name": 3,       # 1-based 4
    "pack": 5,       # 1-based 6
    "price": 7,      # 1-based 8
    "stock": 8,      # 1-based 9
}

def parse_int(s: str):
    m = _rx_int.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None

def discount_round(price: int, rate: float = 0.10, unit: int = 100) -> int:
    if price is None:
        return None
    val = Decimal(price) * Decimal(1 - rate)  # 10% 할인
    return int((val / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit)

def safe_text(loc, fallback=""):
    try:
        return loc.inner_text().strip()
    except Exception:
        return fallback

def find_search_input(page):
    for sel in (
        "form input[type='search']","form input[type='text']",
        "input[type='search']","input[type='text']",
        "input[placeholder*='검색']","input[placeholder*='search' i]"
    ):
        loc = page.locator(sel)
        if loc.count():
            return loc.first
    raise RuntimeError("검색 입력창을 찾지 못했습니다.")

# --- idx 추출: //*[@id='result_list']/div[2]/form/table/tbody/tr/td[4]/a 에서 href/onclick에서 확보 ---
def extract_idx_from_anchor(a):
    try:
        onclick = a.get_attribute("onclick") or ""
        href    = a.get_attribute("href") or ""
    except Exception:
        onclick = ""; href = ""
    s = f"{onclick} {href}"
    m = _rx_idx.search(s)
    if not m:
        return None
    return (m.group(1) or m.group(2))

# --- 팝업 라벨 수집: 직접 URL 접속 + control_wrap2 > p.pp ---
def fetch_labels_by_anchor(ctx, anchor):
    idx = extract_idx_from_anchor(anchor)
    if not idx:
        return []  # idx가 확실히 여기 있다 하셨으니 보통 이 케이스는 없음

    url = f"{BASE}/02_product/search/popup/?idx={idx}"
    pop = ctx.new_page()
    try:
        pop.set_default_timeout(DEFAULT_TIMEOUT)
        # 팝업 페이지에서 이미지/폰트는 차단 (속도)
        def _route(route):
            if route.request.resource_type in {"image","font","media"}:
                return route.abort()
            return route.continue_()
        pop.route("**/*", _route)

        pop.goto(url, wait_until="domcontentloaded")
        # div.control_wrap2 내부 p.pp가 보일 때까지 조금 기다림
        try:
            pop.wait_for_selector("div.control_wrap2 p.pp", timeout=DEFAULT_TIMEOUT)
        except Exception:
            # DOM 삽입 지연 대비 한번 더
            try:
                pop.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass

        pps = pop.locator("div.control_wrap2 p.pp")
        cnt = pps.count()
        out = []
        for i in range(cnt):
            t = safe_text(pps.nth(i))
            if t and t not in out:
                out.append(re.sub(r"\s+", " ", t))
        return out
    except Exception:
        return []
    finally:
        try:
            pop.close()
        except Exception:
            pass

def search_minimal(keyword: str, first_only: bool = True, include_labels: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)

        page.goto(SEARCH_URL, wait_until="domcontentloaded")
        box = find_search_input(page)
        box.fill(""); box.type(keyword); box.press("Enter")

        try:
            page.wait_for_selector("tbody tr", timeout=3000)
        except Exception:
            btns = page.locator("form button, button[type='submit'], input[type='submit']")
            if btns.count():
                btns.first.click()
            page.wait_for_selector("tbody tr", timeout=3000)

        rows = page.locator("tbody tr")
        n = rows.count()
        if n == 0:
            return []

        items = []
        for i in range(n):
            tds = rows.nth(i).locator("td")
            if tds.count() <= TD_IDX["stock"]:
                continue

            code = safe_text(tds.nth(TD_IDX["code"])) or None
            price = parse_int(safe_text(tds.nth(TD_IDX["price"])))
            stock_label = safe_text(tds.nth(TD_IDX["stock"]))

            labels = []
            name_a = tds.nth(TD_IDX["name"]).locator("a")
            if include_labels and name_a.count():
                labels = fetch_labels_by_anchor(ctx, name_a.first)

            items.append({
                "brand": "대정화금",
                "code": code,
                "price": price,
                "discount_price": discount_round(price, unit=100),
                "stock_label": stock_label,
                "labels": labels,
            })

            if first_only:
                break

        browser.close()
        return items

if __name__ == "__main__":
    kw = input("🔎 대정 제품코드 또는 키워드(하이픈 포함): ").strip()
    data = search_minimal(kw)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
