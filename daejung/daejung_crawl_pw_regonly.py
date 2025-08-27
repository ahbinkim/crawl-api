# -*- coding: utf-8 -*-
"""
대정 검색 최소 데이터 수집 (팝업-클릭 방식)
- Render 지연 대비: 탐색 타임아웃 분리 + 재시도
"""
from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True

# ⬇ 요소/액션 기본 대기(입력/클릭 등): 8~10초 권장
DEFAULT_TIMEOUT = 9000
# ⬇ 페이지 이동(네비게이션) 전용 대기: 25~30초 권장
NAV_TIMEOUT = 30000

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
        pop.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
    except Exception:
        pass
    labels = extract_regulation_lines(pop)
    try:
        pop.close()
    except Exception:
        pass
    return labels

def _goto_with_retry(page, url, attempts=2):
    last = None
    for i in range(attempts):
        try:
            # 1차: domcontentloaded 까지 대기
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            return True
        except Exception as e:
            last = e
            # 2차: 더 관대한 모드(커밋 후 DOM 준비를 별도로 대기)
            try:
                page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT)
                page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
                return True
            except Exception as e2:
                last = e2
                # 소폭 대기 후 재시도
                try:
                    page.wait_for_timeout(1200 * (i + 1))
                except Exception:
                    pass
    # 디버그 스냅샷
    ts = int(time.time())
    try:
        page.screenshot(path=f"daejung_debug_goto_{ts}.png", full_page=True)
        with open(f"daejung_debug_goto_{ts}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass
    raise last if last else RuntimeError("goto failed")

def search_minimal(keyword: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        ctx = browser.new_context()
        page = ctx.new_page()
        # ⬇ 두 타임아웃을 분리 설정 (중요!)
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(NAV_TIMEOUT)

        # 1) 검색 페이지 진입(재시도 포함)
        _goto_with_retry(page, SEARCH_URL, attempts=2)

        # 2) 검색어 입력 → 엔터
        box = find_search_input(page)
        box.fill(""); box.type(keyword); box.press("Enter")

        # 3) 결과 대기 + 폴백 버튼 제출
        try:
            page.wait_for_selector("tbody tr", timeout=7000)
        except Exception:
            try:
                page.locator("form button, button[type='submit'], input[type='submit']").first.click()
                page.wait_for_selector("tbody tr", timeout=7000)
            except Exception:
                ts = int(time.time())
                page.screenshot(path=f"daejung_debug_{ts}.png", full_page=True)
                with open(f"daejung_debug_{ts}.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                browser.close()
                return []

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

            # 팝업에서 규제 라벨만 추출 (실제 클릭)
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




