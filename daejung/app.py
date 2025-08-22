from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Any, List, Union

from daejung_crawl_pw_regonly import search_minimal

# (선택) ping을 daejung_crawl_pw_regonly.py에 넣어두셨다면 가져오세요.
try:
    from daejung_crawl_pw_regonly import ping
except Exception:
    ping = lambda: "ping-unavailable"

app = FastAPI(title="Daejung Crawl API")

@app.get("/healthz")
def healthz():
    # ping 결과도 같이 보여주면 네트워크/차단 여부를 바로 확인 가능
    return {"ok": True, "ping": ping()}

@app.get("/search")
def search(
    kw: str = Query(..., description="대정 제품코드 또는 키워드"),
    first_only: bool = Query(False, description="첫 결과만 반환")
) -> Union[List[Any], Any]:
    try:
        data = search_minimal(kw)
        return (data[0] if (first_only and data) else ({} if first_only else data))
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # 로그에도 상세 출력
        print("SEARCH_ERROR:", e, tb)
        # 브라우저에도 에러를 직접 내려줌 (원인 파악용)
        return JSONResponse(status_code=500, content={"error": str(e), "trace": tb})

