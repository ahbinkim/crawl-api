# -*- coding: utf-8 -*-
"""
대정 최소 데이터 수집 (Playwright 안정화판)
- 검색/테이블 파싱은 기존 로직 유지
- 팝업: idx 추출 후 직접 URL 접속
- 라벨: div.control_wrap2 p.pp 텍스트 수집 (main + iframe 모두)
- Render 환경: 타임아웃 상향, commit+selector 대기, 리소스 차단
"""

from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time, urllib.request

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True

DEFAULT_TIMEOUT = 20000   # 요소 대기(ms)
GOTO_TIMEOUT    = 30000   # 페이지 진입(ms)

LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_rx_int = re.compile(r"(\d[\d,]*)")
_rx_idx = re.compile(r"/popup/\?idx=(\d{4})|idx\s*=\s*(\d{4})", re.I)

TD_IDX = {
    "cas": 1,
    "code": 2,
    "name": 3,
    "pack": 5,
    "price": 7,
    "stock": 8,
}

# ---- health check ----
def ping():
    try:
        with urllib.request.urlopen(SEARCH_URL, timeout=8) as r:
            return r.status
    except Exception as e:
        return f"ERR:{e}"

# ---- helpers ----
def parse_int(s: str):
    m = _rx_int.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None

def discount_round(price: int, rate: float = 0.10, unit: int = 100) -> int:
    if price is None:
        return None
    val = Decimal(price) * Decimal(1 - rate)
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

# ---- 팝업 라벨 수집 ----
def fetch_labels_by_anchor(ctx, anchor):
    idx = extract_idx_from_anchor(anchor)
    if not idx:
        return []

    url = f"{BASE}/02_product/search/popup/?idx={idx}"
    pop = ctx.new_page()
    try:
        pop.set_default_timeout(DEFAULT_TIMEOUT)
        pop.set_default_navigation_timeout(GOTO_TIMEOUT)

        # 불필요 리소스 차단
        def _route(route):
            if route.request.resource_type in {"image","font","media"}:
                return route.abort()
            return route.continue_()
        pop.route("**/*", _route)

        pop.goto(url, wait_until="load", timeout=GOTO_TIMEOUT)
        try:
            pop.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass

        selector = "div.control_wrap2 p.pp"
        texts = []

        # main frame
        try:
            pop.wait_for_selector(selector, timeout=DEFAULT_TIMEOUT)
            texts += pop.eval_on_selector_all(
                selector, "els => els.map(e => (e.textContent || '').trim())"
            )
        except Exception:
            pass

        # iframe들
        for fr in pop.frames:
            if fr == pop.main_frame:
                continue
            try:
                fr.wait_for_selector(selector, timeout=2000)
                texts += fr.eval_on_selector_all(
                    selector, "els => els.map(e => (e.textContent || '').trim())"
                )
            except Exception:
                continue

        # 정리
        out, seen = [], set()
        for t in texts:
            if not t:
                continue
            t = re.sub(r"\s+", " ", t).strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)

        return out
    except Exception:
        return []
    finally:
        try:
            pop.close()
        except Exception:
            pass

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
            page.wait_for_timeout(1500 * (i + 1))
            try:
                page.reload(timeout=GOTO_TIMEOUT)
            except Exception:
                pass
    raise last_err

# ---- main search ----
def search_minimal(keyword: str, first_only: bool = True, include_labels: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        ctx = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/123.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(GOTO_TIMEOUT)

        # 검색 페이지 리소스 차단
        def _route(route):
            if route.request.resource_type in {"image", "font", "media"}:
                return route.abort()
            return route.continue_()
        page.route("**/*", _route)

        goto_with_retry(page, SEARCH_URL, attempts=3)

        # 검색
        box = find_search_input(page)
        box.fill(""); box.type(keyword); box.press("Enter")

        try:
            page.wait_for_selector("tbody tr", timeout=DEFAULT_TIMEOUT)
        except Exception:
            btns = page.locator("form button, button[type='submit'], input[type='submit']")
            if btns.count():
                btns.first.click()
            page.wait_for_selector("tbody tr", timeout=DEFAULT_TIMEOUT)

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
            if include_labels:
                name_a = tds.nth(TD_IDX["name"]).locator("a")
                if name_a.count():
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
    data = search_minimal(kw or "4016-4400", first_only=True, include_labels=True)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
