# -*- coding: utf-8 -*-
"""
대정 검색 최소 데이터 수집 (가성비 & 속도 최적화판 - labels 개선 풀버전)
- 브라우저 1회만 띄우고 재사용 (싱글톤)
- 이미지/폰트/미디어 차단(스크립트는 허용) → 동적 렌더링 유지
- 첫 결과만/라벨 포함 여부 옵션
- ✅ 팝업 클릭 X → onclick/href/행 전체에서 idx 추출 후 popup URL로 직접 접속
- ✅ 팝업이 iframe/동적삽입이어도 파싱되도록 '프레임 순회 + 로딩 대기' 강화
- ✅ 실패 시 1회 디버그 덤프(HTML, 프레임 본문)로 원인 고정
"""

from playwright.sync_api import sync_playwright
from decimal import Decimal, ROUND_HALF_UP
import re, json, time, urllib.request, os
from typing import Optional

# -------------------- 상수 --------------------
BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True

DEFAULT_TIMEOUT = 15000   # 요소 대기(ms)
GOTO_TIMEOUT = 25000      # 페이지 진입(ms)

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

# -------------------- 싱글톤 브라우저 --------------------
_play = None
_browser = None

def get_browser():
    global _play, _browser
    if _play is None:
        _play = sync_playwright().start()
    if _browser is None:
        _browser = _play.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
    return _browser

def stop_browser():
    global _play, _browser
    try:
        if _browser: _browser.close()
    except Exception:
        pass
    try:
        if _play: _play.stop()
    except Exception:
        pass
    _browser = None; _play = None

# -------------------- 유틸 --------------------
def ping():
    try:
        with urllib.request.urlopen(SEARCH_URL, timeout=8) as r:
            return r.status
    except Exception as e:
        return f"ERR:{e}"

def parse_int(s: str) -> Optional[int]:
    m = _rx_int.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None

def discount_round(price: Optional[int], rate: float = 0.10, unit: int = 100) -> Optional[int]:
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

# -------------------- idx 추출 (행 전체 커버) --------------------
IDX_RXES = [
    re.compile(r"idx\s*=\s*([A-Za-z0-9_-]+)"),
    re.compile(r"popup[^)]*?\bidx[^A-Za-z0-9_-]*?([A-Za-z0-9_-]+)"),
    re.compile(r"\bfn_\w+\s*\(\s*([A-Za-z0-9_-]+)\s*\)"),
    re.compile(r"data-idx\s*=\s*['\"]?([A-Za-z0-9_-]+)['\"]?"),
    re.compile(r"/popup/\?idx=([A-Za-z0-9_-]+)"),
]

def extract_idx_from_row(row) -> Optional[str]:
    # 제품명 앵커 우선
    try:
        a = row.locator("td").nth(TD_IDX['name']).locator("a")
        onclick = a.first.get_attribute("onclick") if a.count() else ""
        href    = a.first.get_attribute("href")    if a.count() else ""
    except Exception:
        onclick = ""; href = ""

    s = f"{onclick or ''} {href or ''}"

    # 행 전체 outerHTML까지 합쳐 패턴 검색
    try:
        outer = row.evaluate("el => el.outerHTML")
        s += " " + (outer or "")
    except Exception:
        pass

    for rx in IDX_RXES:
        m = rx.search(s)
        if m:
            return m.group(1)
    return None

# -------------------- 팝업 파싱 보조 --------------------
def extract_texts_from_page_or_frames(p):
    """본문 텍스트를 메인 body + 모든 iframe의 body에서 수집"""
    texts = []
    # 1) 메인
    try:
        body = p.inner_text("body")
        if body and body.strip():
            texts.append(body)
    except Exception:
        pass
    # 2) 프레임
    try:
        for fr in p.frames:
            if fr == p.main_frame:
                continue
            try:
                b = fr.inner_text("body")
                if b and b.strip():
                    texts.append(b)
            except Exception:
                continue
    except Exception:
        pass
    return texts

def extract_regulation_lines(page):
    """팝업에서 규제정보 관련 줄만 추출 (표 우선 → 본문/프레임 보조)"""
    lines = []
    # 표 우선 파싱
    try:
        tds = page.locator("table td, .popup table td, .table td, .layer table td")
        if tds.count() > 0:
            for i in range(tds.count()):
                txt = (tds.nth(i).inner_text() or "").strip()
                if txt:
                    lines.append(txt)
    except Exception:
        pass

    # 표가 없거나 부족하면 본문/프레임
    if not lines:
        try:
            blobs = extract_texts_from_page_or_frames(page)
            raw = "\n".join(blobs)
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        except Exception:
            lines = []

    keep_keys = (
        "물질","류","유해","위험","규제","Remark","기존물질","유해화학물질",
        "신규화학물질","기존 화학물질","산업안전보건법","화학물질","관계법령"
    )
    kept = [ln for ln in lines if any(k in ln for k in keep_keys)]

    # 중복 제거 + 공백 정리
    seen, out = set(), []
    for ln in kept:
        ln2 = re.sub(r"\s+", " ", ln)
        if ln2 not in seen:
            out.append(ln2); seen.add(ln2)
    return out

def debug_dump_popup(p, prefix="popup"):
    """문제 원인 고정을 위한 1회 덤프"""
    try:
        os.makedirs("debug_dump", exist_ok=True)
        with open(os.path.join("debug_dump", f"{prefix}_main.html"), "w", encoding="utf-8") as f:
            f.write(p.content())
        for i, fr in enumerate(p.frames):
            try:
                b = fr.inner_text("body")
                with open(os.path.join("debug_dump", f"{prefix}_frame_{i}.txt"), "w", encoding="utf-8") as f:
                    f.write(b or "")
            except Exception:
                pass
    except Exception:
        pass

# ✅ 팝업 클릭 없이, idx를 이용해 직접 팝업 URL 접속 → 라벨 추출
def fetch_labels_by_idx(ctx, idx: str) -> list[str]:
    url = f"{BASE}/02_product/popup/?idx={idx}"
    p = ctx.new_page()
    try:
        p.set_default_timeout(DEFAULT_TIMEOUT)
        p.set_default_navigation_timeout(GOTO_TIMEOUT)

        # 팝업 페이지에도 리소스 라우팅 적용 (script 허용)
        def _route(route):
            if route.request.resource_type in {"image","font","media"}:
                return route.abort()
            return route.continue_()
        p.route("**/*", _route)

        # load까지 대기 + networkidle 보조
        p.goto(url, wait_until="load", timeout=GOTO_TIMEOUT)
        try:
            p.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass

        # 동적 삽입 대비 짧은 재확인 루프
        for _ in range(2):
            # 표/컨테이너 존재 확인 후 약간 더 대기
            if p.locator("table, .popup, .layer, body").count() > 0:
                try:
                    p.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass
            txts = extract_texts_from_page_or_frames(p)
            if any(len(t.strip()) > 50 for t in txts):
                break
            p.wait_for_timeout(600)

        labels = extract_regulation_lines(p)
        if not labels:
            # 최초 실패 시 덤프
            debug_dump_popup(p, prefix=f"popup_idx_{idx}")
        return labels

    except Exception:
        return []
    finally:
        try:
            p.close()
        except Exception:
            pass

# -------------------- 메인 검색 --------------------
def search_minimal(keyword: str, first_only: bool = False, include_labels: bool = False):
    """필수 최소 데이터만 수집
    - first_only: 첫 행만 반환(가장 빠름)
    - include_labels: 필요할 때만 라벨 수집(팝업 URL 직접 접속)
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

    browser = get_browser()
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        viewport={"width": 1366, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    # 자동화 탐지 우회 작은 보정
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

    page = ctx.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(GOTO_TIMEOUT)

    # 리소스 절감: 이미지/폰트/미디어 차단 (script 허용)
    def _route(route):
        if route.request.resource_type in {"image", "font", "media"}:
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

    # 첫 행 디버그(1회) - idx/앵커 속성 확인 용
    debug_dumped_row = False

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
            idx = extract_idx_from_row(rows.nth(i))
            if not debug_dumped_row:
                try:
                    row_html = rows.nth(i).evaluate("el => el.outerHTML")
                    os.makedirs("debug_dump", exist_ok=True)
                    with open(os.path.join("debug_dump", "row_debug.html"), "w", encoding="utf-8") as f:
                        f.write(row_html or "")
                    a = rows.nth(i).locator("td").nth(TD_IDX['name']).locator("a")
                    if a.count():
                        with open(os.path.join("debug_dump", "a_debug.txt"), "w", encoding="utf-8") as f:
                            f.write("onclick=" + str(a.first.get_attribute("onclick")) + "\n")
                            f.write("href=" + str(a.first.get_attribute("href")) + "\n")
                except Exception:
                    pass
                debug_dumped_row = True

            labels = fetch_labels_by_idx(ctx, idx) if idx else []

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

    ctx.close()
    return items

# -------------------- CLI 실행 --------------------
if __name__ == "__main__":
    try:
        kw = input("🔎 대정 제품코드 또는 키워드: ").strip()
    except EOFError:
        kw = ""
    data = search_minimal(kw or "에탄올", first_only=True, include_labels=True)
    print(json.dumps(data, ensure_ascii=False, indent=2) if data else "❌ 결과 없음")
