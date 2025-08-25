from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Any, List, Union

from daejung_crawl_pw_regonly import search_minimal

# Optional: import ping if present (not required for boot)
try:
    from daejung_crawl_pw_regonly import ping  # type: ignore
except Exception:
    ping = None  # type: ignore

app = FastAPI(title="Daejung Crawl API")

@app.get("/")
def home():
    return JSONResponse({
        "service": "Daejung Crawl API",
        "health": "/healthz",
        "search_examples": [
            "/search?q=5062-8825",
            "/search?q=질산%20란타늄",
            "/search?q=5062-8825&first_only=true"
        ],
        "docs": "/docs"
    })

@app.get("/healthz")
def healthz():
    val = None
    if ping:
        try:
            val = ping()
        except Exception as e:
            val = f"ERR:{e}"
    return {"ok": True, "ping": val}

@app.get("/search")
def search(
    q: str = Query(..., description="검색어 (제품코드 또는 키워드)"),
    first_only: bool = Query(False, description="첫 결과만 반환")
) -> Union[List[Any], Any]:
    try:
        data = search_minimal(q)
        return (data[0] if (first_only and data) else ({} if first_only else data))
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})
