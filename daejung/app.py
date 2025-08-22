from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Any, List, Union
from daejung_crawl_pw_regonly import search_minimal

app = FastAPI(title="Daejung Crawl API")

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/search")
def search(
    q: str = Query(..., description="검색어 (제품코드 또는 키워드)"),
    first_only: bool = Query(False, description="첫 결과만 반환")
) -> Union[list[Any], Any]:
    try:
        data = search_minimal(q)
        return (data[0] if (first_only and data) else ({} if first_only else data))
    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

