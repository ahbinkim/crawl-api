from fastapi import FastAPI, Query
from typing import Any, List, Union
from daejung_crawl_pw_regonly import search_minimal

app = FastAPI(title="Daejung Crawl API")

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/search")
def search(kw: str = Query(..., description="대정 제품코드 또는 키워드"),
           first_only: bool = Query(False, description="첫 결과만 반환")) -> Union[List[Any], Any]:
    data = search_minimal(kw)
    if first_only:
        return (data[0] if data else {})
    return data
