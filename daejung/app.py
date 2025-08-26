
# -*- coding: utf-8 -*-
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import time

from daejung_crawl_pw_regonly import search_minimal, stop_browser

# --- ultra-light in-memory cache (helps after cold start) ---
CACHE_TTL_SEC = 30
_cache: Dict[tuple, tuple[float, Any]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # start
    yield
    # stop
    try:
        stop_browser()
    except Exception:
        pass

app = FastAPI(title="Daejung Crawl API", lifespan=lifespan)

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"

@app.get("/")
def home():
    return JSONResponse({
        "service": "Daejung Crawl API",
        "endpoints": ["/search", "/healthz"],
        "ttl_seconds": CACHE_TTL_SEC
    })

@app.get("/search")
def search(
    q: str = Query(..., description="Search keyword (CAS, code, name, etc.)"),
    first_only: bool = Query(False, description="Return only first row"),
    include_labels: bool = Query(True, description="Fetch popup labels"),
):
    key = (q, first_only, include_labels)
    now = time.time()
    ent = _cache.get(key)
    if ent and ent[0] > now:
        return ent[1]

    try:
        data = search_minimal(q, first_only=first_only, include_labels=include_labels)
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": str(e),
            "q": q
        })

    # cache
    _cache[key] = (now + CACHE_TTL_SEC, data)
    return data
