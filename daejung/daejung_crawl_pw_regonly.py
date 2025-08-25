# daejung_crawl_pw_regonly.py (fresh, resilient)
from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time, urllib.request

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True
DEFAULT_TIMEOUT = 15000          # generic wait (ms)
GOTO_TIMEOUT = 25000             # navigation wait (ms)

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

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

def ping():
    try:
        with urllib.request.urlopen(SEARCH_URL, timeout=8) as r:
            return r.status
    except Exception as e:
        return f"ERR:{e}"

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
    import time
    def goto_with_retry(page, url, attempts=3):
        last_err = None
        for i in range(attempts):
            try:
                page.goto(url, wait_until="commit", timeout=GOTO_TIMEOUT)
                page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
                page.wait_for_selector(
                    "form input[type='search'], form input[type='text'], input[placeholder*='검색'], input[placeholder*='search' i]",
                    timeout=DEFAULT_TIMEOUT
                )
                return
            except Exception as e:
                last_err = e
                page.wait_for_timeout(1200 * (i + 1))
                try:
                    page.reload(timeout=GOTO_TIMEOUT)
                except Exception:
                    pass
        raise last_err

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        # 헤드리스 탐지 흔적 제거(안정성↑)
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(GOTO_TIMEOUT)

        # 불필요 리소스 차단(로딩 안정화)
        def _route(route):
            if route.request.resource_type in {"image", "font"}:
                return route.abort()
            return route.continue_()
        page.route("**/*", _route)

        # 1) 검색 페이지 진입(재시도)
        goto_with_retry(page, SEARCH_URL, attempts=3)

        # 2) 검색어 입력 → 엔터
        box = find_search_input(page)
        box.fill("")
        box.type(keyword)
        box.press("Enter")

        # 3) 결과 대기(버튼 제출 보조 + 재시도)
        try:
            page.wait_for_selector("tbody tr", timeout=DEFAULT_TIMEOUT)
        except Exception:
            btn = page.locator("form button, button[type='submit'], input[type='submit']")
            if btn.count():
                btn.first.click()
            page.wait_for_selector("tbody tr", timeout=DEFAULT_TIMEOUT)

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
