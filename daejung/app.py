# -*- coding: utf-8 -*-
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Any, List, Union
import time

# 같은 폴더에 있다고 가정
from daejung_crawl_pw_regonly import (
    search_minimal, ping
)

# --- 아주 가벼운 메모리 캐시(콜드 스타트 이후 체감↑) ---
CACHE_TTL = 30  # 초
_cache: dict[tuple, tuple[float, list]] = {}  # key -> (expire, data)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # start: 아무 것도 안함
    yield
    # stop: 브라우저 정리(컨테이너 종료 시)
    try:
        stop_browser()
    except Exception:
        pass

app = FastAPI(title="Daejung Crawl API", lifespan=lifespan)

@app.get("/")
def home():
    return JSONResponse({
        "service": "Daejung Crawl API",
        "health": "/healthz",
        "examples": [
            "/search?q=5062-8825",
            "/search?q=질산%20란타늄&first_only=true",
            "/search?q=5062-8825&first_only=true&include_labels=true"
        ],
        "docs": "/docs"
    })

@app.get("/healthz")
def healthz():
    v = None
    try:
        v = ping()
    except Exception as e:
        v = f"ERR:{e}"
    return {"ok": True, "ping": v}

@app.get("/search")
def search(
    q: str = Query(..., description="검색어(제품코드/키워드)"),
    first_only: bool = Query(False, description="첫 행만 반환(빠름)"),
    include_labels: bool = Query(False, description="라벨(팝업) 수집 여부(느림)")
) -> Union[List[Any], Any]:
    try:
        key = (q, first_only, include_labels)
        now = time.time()
        hit = _cache.get(key)
        if hit and hit[0] > now:
            data = hit[1]
        else:
            data = search_minimal(q, first_only=first_only, include_labels=include_labels)
            _cache[key] = (now + CACHE_TTL, data)

        return (data[0] if (first_only and data) else ({} if first_only else data))
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})
