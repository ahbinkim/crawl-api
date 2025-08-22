from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Any, List, Union
from daejung_crawl_pw_regonly import search_minimal

try:
    from daejung_crawl_pw_regonly import ping
except Exception:
    ping = None

app = FastAPI(title="Daejung Crawl API")

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/search")
def search(
    q: str = Query(..., description="검색어 (제품코드 또는 키워드)"),
    first_only: bool = Query(False, description="첫 결과만 반환")
):
    data = search_minimal(q)
    return (data[0] if (first_only and data) else ({} if first_only else data))
