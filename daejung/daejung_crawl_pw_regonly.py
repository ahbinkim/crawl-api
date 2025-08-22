# daejung_crawl_pw_regonly.py (indices updated, with Render launch args)
from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time

# 꼭 상단에 추가
import urllib.request
def ping():
    try:
        with urllib.request.urlopen(SEARCH_URL, timeout=10) as r:
            return r.status
    except Exception as e:
        return f"ERR: {e}"
print("PING:", ping())


BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True
DEFAULT_TIMEOUT = 4000

# Render/containers: recommended browser flags
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_rx_int = re.compile(r"(\d[\d,]*)")

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

def extract_regulation_lines(p):
    """팝업에서 규제정보 관련 줄만 추출"""
    try:
        raw = p.inner_text("body").strip()
    except Exception:
        raw = ""

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # 규제 관련 키워드가 들어간 줄만 필터
    keep_keys = ("물질", "류", "유해", "위험", "규제", "Remark", "기존물질")
    kept = [ln for ln in lines if any(k in ln for k in keep_keys)]

    # 중복 제거
    seen, out = set(), []
    for ln in kept:
        if ln not in seen:
            out.append(ln); seen.add(ln)
    return out


def open_popup_and_get_labels(page, anchor):
    try:
        with page.expect_popup() as pop_info:
            anchor.click()
        pop = pop_info.value
    except Exception:
        return []
    try:
        pop.wait_for_load_state("domcontentloaded")
    except Exception:
        pass
    labels = extract_regulation_lines(pop)
    try:
        pop.close()
    except Exception:
        pass
    return labels

def search_minimal(keyword: str):
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
            page.locator("form button, button[type='submit'], input[type='submit']").first.click()
            page.wait_for_selector("tbody tr", timeout=3000)

        rows = page.locator("tbody tr")
        n = rows.count()
        if n == 0:
            ts = int(time.time())
            page.screenshot(path=f"daejung_debug_{ts}.png", full_page=True)
            with open(f"daejung_debug_{ts}.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            browser.close()
            return []

        items = []
        for i in range(n):
            tds = rows.nth(i).locator("td")
            if tds.count() <= TD_IDX["stock"]:
                continue

            code = safe_text(tds.nth(TD_IDX["code"])) or None
            price = parse_int(safe_text(tds.nth(TD_IDX["price"])))
            stock_label = safe_text(tds.nth(TD_IDX["stock"]))

            # 팝업에서 규제 라벨만 추출
            name_a = tds.nth(TD_IDX["name"]).locator("a")
            labels = open_popup_and_get_labels(page, name_a.first) if name_a.count() else []

            items.append({
                "brand": "대정화금",
                "code": code,
                "price": price,
                "discount_price": discount_round(price, unit=100),
                "stock_label": stock_label,
                "labels": labels,
            })

        browser.close()
        return items

if __name__ == "__main__":
    kw = input("🔎 대정 제품코드 또는 키워드: ").strip()
    data = search_minimal(kw)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
