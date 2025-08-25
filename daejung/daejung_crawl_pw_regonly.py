# -*- coding: utf-8 -*-
"""
대정 검색 최소 데이터 수집 (가성비 & 속도 최적화판)

- 브라우저 1회만 띄우고 재사용 (무료 플랜에서도 빠르게)
- 이미지/폰트 차단으로 네트워크 절감
- 첫 결과만/라벨(팝업) 포함 여부를 옵션으로 제어
- 견고한 대기/재시도 로직
"""

from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time, urllib.request

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True

# 시간값: 너무 짧으면 타임아웃, 너무 길면 느림 → 현실적인 타협
DEFAULT_TIMEOUT = 15000   # 요소 대기(ms)
GOTO_TIMEOUT = 25000      # 페이지 진입(ms)

# 저가형 컨테이너/무료플랜 안정화 옵션
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

# ---------- 브라우저 싱글톤 (가성비 핵심) ----------
_play = None
_browser = None

def get_browser():
    """컨테이너가 살아있는 동안 브라우저 1개만 재사용."""
    global _play, _browser
    if _play is None:
        _play = sync_playwright().start()
    if _browser is None:
        _browser = _play.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
    return _browser

def stop_browser():
    """FastAPI 종료 시 호출 (메모리/프로세스 정리)."""
    global _play, _browser
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _play:
            _play.stop()
    except Exception:
        pass
    _browser = None
    _play = None

# ---------- 보조 유틸 ----------
def ping():
    try:
        with urllib.request.urlopen(SEARCH_URL, timeout=8) as r:
            return r.status
    except Exception as e:
        return f"ERR:{e}"

def parse_int(s: str):
    m = _rx_int.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None

def discount_round(price: int, rate: float = 0.10, unit: int = 100) -> int | None:
    """10% 할인 후 100원 단위 반올림."""
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

def extract_regulation_lines(p):
    """팝업에서 규제정보 관련 줄만 추출(간결/가벼움)."""
    try:
        raw = p.inner_text("body").strip()
    except Exception:
        raw = ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
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

# ---------- 메인 크롤 함수 ----------
def search_minimal(keyword: str, first_only: bool = False, include_labels: bool = False):
    """필수 최소 데이터만 수집 (가성비 모드)
    - first_only: 첫 행만 반환(가장 빠름)
    - include_labels: 필요할 때만 팝업 라벨 수집(느림)
    """
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

    # 브라우저 재사용 → 매 요청은 컨텍스트만 생성
    browser = get_browser()
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        viewport={"width": 1366, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    # 헤드리스 탐지 흔적 제거
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

    page = ctx.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(GOTO_TIMEOUT)

    # 리소스 절감(속도↑): 이미지/폰트 차단
    def _route(route):
        if route.request.resource_type in {"image", "font"}:
            return route.abort()
        return route.continue_()
    page.route("**/*", _route)

    # 1) 검색 페이지 진입
    goto_with_retry(page, SEARCH_URL, attempts=3)

    # 2) 검색어 입력 → 엔터
    box = find_search_input(page)
    box.fill("")
    box.type(keyword)
    box.press("Enter")

    # 3) 결과 대기(제출 버튼 보조)
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
        ctx.close()
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
        if include_labels and (not first_only or i == 0):
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

        if first_only:
            break

    ctx.close()  # 브라우저는 유지, 컨텍스트만 닫기
    return items

if __name__ == "__main__":
    kw = input("🔎 대정 제품코드 또는 키워드: ").strip()
    data = search_minimal(kw, first_only=True)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
