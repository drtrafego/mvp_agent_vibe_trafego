import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()

RAILWAY_URL = "https://agentevibe.casaldotrafego.com"

_SKIP_HEADERS = {"host", "content-length", "transfer-encoding"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(request: Request, path: str):
    url = f"{RAILWAY_URL}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=await request.body(),
            params=dict(request.query_params),
        )

    resp_headers = {k: v for k, v in response.headers.items() if k.lower() not in {"content-encoding", "transfer-encoding"}}
    return Response(content=response.content, status_code=response.status_code, headers=resp_headers)
