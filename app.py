from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from daejung_crawl_pw_regonly import search_minimal

app = FastAPI(title="Daejung Crawl API")

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"

@app.get("/search")
def search(q: str = Query(..., description="검색어 (코드/키워드)")):
    try:
        data = search_minimal(q)
        return data
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
