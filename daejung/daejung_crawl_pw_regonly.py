
# -*- coding: utf-8 -*-
"""
Daejung minimal crawler (Playwright stable, popup labels included)

- Search page parse: table parse as before (CAS/Code/Name/Pack/etc.)
- Popup labels: extract idx, then open popup URL directly
- Label collection: from div.control_wrap2 p.pp on main and (if present) iframe
- Render-friendly: higher timeouts, resource blocking (images/fonts/media), robust waits
- Works headless by default; Chromium via Playwright
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional, Tuple
import re, json, time

BASE = "https://www.daejungchem.co.kr"
SEARCH_URL = f"{BASE}/02_product/search/"
HEADLESS = True

DEFAULT_TIMEOUT = 25000   # ms, selector waits
GOTO_TIMEOUT    = 35000   # ms, page goto

LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_rx_int = re.compile(r"(\d[\d,]*)")
_rx_popup_idx = re.compile(r"idx=([0-9]+)")

TD_IDX = {
    "cas": 1,
    "code": 2,
    "name": 3,
    "pack": 5
}

def _clean(s: Any) -> str:
    return (s or "").strip()

def _extract_int(s: str) -> Optional[int]:
    m = _rx_int.search(s or "")
    if not m:
        return None
    return int(m.group(1).replace(",", ""))

def _parse_table_row(tr) -> Optional[Dict[str, Any]]:
    tds = tr.query_selector_all("td")
    if not tds or len(tds) < 6:
        return None

    def txt(i: int) -> str:
        try:
            return _clean(tds[i].inner_text())
        except Exception:
            return ""

    # Try to find popup anchor in the last column
    try:
        # Commonly last td contains anchor for popup
        last_td = tds[-1]
        a = last_td.query_selector("a")
        href = a.get_attribute("href") if a else None
    except Exception:
        href = None

    item = {
        "cas": txt(TD_IDX["cas"]),
        "code": txt(TD_IDX["code"]),
        "name": txt(TD_IDX["name"]),
        "pack": txt(TD_IDX["pack"]),
        "popup_href": href,
    }
    return item

def _extract_idx_from_href(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    m = _rx_popup_idx.search(href)
    if not m:
        return None
    return m.group(1)

def _route_block(route):
    # block heavy non-essential resources
    try:
        if route.request.resource_type in ("image", "media", "font"):
            return route.abort()
    except Exception:
        pass
    return route.continue_()

def _collect_labels_from_popup(page, idx: str) -> List[str]:
    url = f"{BASE}/02_product/popup/?idx={idx}"
    page.goto(url, timeout=GOTO_TIMEOUT, wait_until="domcontentloaded")
    # wait for container (best-effort; some popups load quickly)
    try:
        page.wait_for_selector("div.control_wrap2", timeout=DEFAULT_TIMEOUT)
    except PlaywrightTimeoutError:
        pass

    labels: List[str] = []

    # JS map must use '||' (not Python 'or')
    map_js = "els => els.map(e => (e.textContent || '').trim()).filter(Boolean)"

    # main document
    try:
        nodes = page.locator("div.control_wrap2 p.pp").element_handles()
        if nodes:
            labels.extend(page.evaluate(map_js, nodes))
    except Exception:
        pass

    # iframes (just in case some labels are inside an iframe)
    try:
        for f in page.frames:
            if f is page.main_frame:
                continue
            try:
                nodes = f.locator("div.control_wrap2 p.pp").element_handles()
                if nodes:
                    labels.extend(f.evaluate(map_js, nodes))
            except Exception:
                continue
    except Exception:
        pass

    # de-dup and clean
    out = []
    seen = set()
    for s in labels:
        s2 = (s or "").strip()
        if not s2:
            continue
        if s2 in seen:
            continue
        seen.add(s2)
        out.append(s2)

    return out

def search_minimal(query: str, *, first_only: bool = False, include_labels: bool = True, debug: bool = False) -> Dict[str, Any]:
    """Run a minimal search and optionally fetch popup labels.

    Returns:
        {
          "q": query,
          "items": [ {cas, code, name, pack, labels?}, ... ],
          "took_ms": int
        }
    """
    t0 = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)

        # block heavy resources
        page.route("**/*", _route_block)

        # open search
        page.goto(SEARCH_URL, timeout=GOTO_TIMEOUT, wait_until="domcontentloaded")
        # Fill search box and submit. The site uses input name 'search_text' typically; adjust if needed
        try:
            page.fill("input[name='search_text']", query)
        except Exception:
            # fallback: a common selector
            page.fill("#search_text", query)

        # click search
        # try several likely selectors to be robust
        clicked = False
        for sel in ["button[type=submit]", "#btn_search", "form[action*=search] button"]:
            try:
                page.click(sel)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            # as a last resort, press Enter
            try:
                page.press("input[name='search_text']", "Enter")
            except Exception:
                pass

        # wait for results table
        # common: table.list_table or table.board_list
        try:
            page.wait_for_selector("table", timeout=DEFAULT_TIMEOUT)
        except PlaywrightTimeoutError:
            pass

        # get rows except header
        rows = page.query_selector_all("table tr")
        items: List[Dict[str, Any]] = []
        for tr in rows:
            try:
                # skip header rows if they contain 'CAS' etc.
                txt = (tr.inner_text() or "").strip()
                if not txt:
                    continue
                if "CAS" in txt and "CODE" in txt and "NAME" in txt:
                    continue

                item = _parse_table_row(tr)
                if not item:
                    continue

                # popup labels
                if include_labels:
                    idx = _extract_idx_from_href(item.get("popup_href"))
                    if idx:
                        try:
                            labels = _collect_labels_from_popup(page, idx)
                        except Exception:
                            labels = []
                        item["labels"] = labels

                # cleanup for output
                item.pop("popup_href", None)
                items.append(item)

                if first_only and items:
                    break
            except Exception:
                continue

        context.close()
        browser.close()

    took = int((time.time() - t0) * 1000)
    return {"q": query, "items": items, "took_ms": took}

def stop_browser():
    """Render's FastAPI lifespan calls this; here it's a no-op because we open/close per request."""
    pass

if __name__ == "__main__":
    # simple manual test
    data = search_minimal("5062-8825", first_only=True, include_labels=True)
    print(json.dumps(data, ensure_ascii=False, indent=2))
