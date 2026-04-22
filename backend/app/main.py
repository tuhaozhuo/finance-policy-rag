from fastapi import FastAPI
from time import perf_counter

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.metrics import metrics_store
from app.db.session import init_db

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def collect_metrics(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    latency_ms = (perf_counter() - start) * 1000
    metrics_store.record(path=request.url.path, status_code=response.status_code, latency_ms=latency_ms)
    return response


@app.on_event("startup")
def on_startup() -> None:
    init_db()
