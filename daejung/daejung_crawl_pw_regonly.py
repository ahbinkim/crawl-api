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


# ---- 팝업 라벨 수집 (클릭 X, idx로 직접 접속 + 디버그) ----
def fetch_labels_by_anchor(ctx, anchor):
    idx = extract_idx_from_anchor(anchor)  # onclick/href에서 idx 추출
    if not idx:
        return []

    url = f"{BASE}/02_product/popup/?idx={idx}"  # ✅ /search/ 없음! 경로 교정
    pop = ctx.new_page()
    try:
        pop.set_default_timeout(DEFAULT_TIMEOUT)
        pop.set_default_navigation_timeout(GOTO_TIMEOUT)

        # 불필요 리소스 차단(이미지/폰트/미디어)
        def _route(route):
            if route.request.resource_type in {"image", "font", "media"}:
                return route.abort()
            return route.continue_()
        pop.route("**/*", _route)

        # ✅ 검색 페이지에서 온 것처럼 Referer를 명시
        pop.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT, referer=SEARCH_URL)

        # 규제정보 헤더가 뜨면 조금 더 대기(동적 로딩 대비)
        try:
            pop.wait_for_selector("text=규제정보", timeout=5000)
        except Exception:
            pass

        # 본문 추출(메인 프레임 + iframe 보조)
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

        # iframes
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

        # 정리(중복 제거 + 공백 정규화)
        out, seen = [], set()
        for t in texts:
            if not t:
                continue
            t = re.sub(r"\s+", " ", t).strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)

        # ✅ 못 찾았으면 HTML 저장(원인 확인용)
        if not out:
            ts = int(time.time())
            with open(f"popup_debug_{idx}_{ts}.html", "w", encoding="utf-8") as f:
                f.write(pop.content())
            print(f"[DEBUG] saved popup html: popup_debug_{idx}_{ts}.html")

        return out
    except Exception as e:
        print("[DEBUG] fetch_labels_by_anchor error:", e)
        return []
    finally:
        try:
            pop.close()
        except Exception:
            pass

# (필요 시) onclick/href에서 idx를 뽑는 보조 함수
def extract_idx_from_anchor(anchor):
    try:
        onclick = anchor.get_attribute("onclick") or ""
        m = re.search(r"popup/\?idx=(\d+)", onclick)
        if m:
            return m.group(1)
        href = anchor.get_attribute("href") or ""
        m2 = re.search(r"popup/\?idx=(\d+)", href)
        if m2:
            return m2.group(1)
    except Exception:
        pass
    return None


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
    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
    viewport={"width": 1366, "height": 900},
    locale="ko-KR",
    timezone_id="Asia/Seoul",
    extra_http_headers={ "Accept-Language": "ko-KR,ko;q=0.9" },  # ✅ 추가
)
        page = ctx.new_page()
        def _resp_logger(r):
            if "/02_product/popup/?" in r.url or "/02_product/search" in r.url:
                print("RES", r.status, r.url)
        page.on("response", _resp_logger)
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
