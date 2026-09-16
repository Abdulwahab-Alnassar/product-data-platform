"""Local API for catalog search, category prediction, and controlled ingestion."""

import logging
import secrets
import threading
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from src.catalog import Catalog
from src.config import Settings
from src.events import EventConflict, ProductEvent, apply_event
from src.monitor import monitor
from src.predict import CategoryModel
from src.qa import answer
from src.search import SearchService


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_name: str = Field(min_length=1, max_length=2000)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    mode: Literal["facts", "ollama"] = "facts"


def create_app(settings=None):
    settings = settings or Settings.from_env()
    catalog = Catalog(settings)
    search = SearchService(catalog)
    app = FastAPI(title="Product Data Platform", version="1.0.0")
    totals = {"requests": 0, "errors": 0, "seconds": 0.0}
    lock = threading.Lock()

    def require_key(x_api_key: str = Header(default="")):
        if not settings.api_key:
            raise HTTPException(
                503, "Write access is disabled. Configure PLATFORM_API_KEY."
            )
        if not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(401, "Invalid API key.")

    def model():
        try:
            return CategoryModel(settings.model_path)
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(
                503, "Train a valid category model before requesting predictions."
            ) from None

    @app.middleware("http")
    async def telemetry(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        with lock:
            totals["requests"] += 1
            totals["errors"] += int(response.status_code >= 400)
            totals["seconds"] += perf_counter() - started
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default errors echo input values; avoid returning submitted data.
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request. See /docs for the accepted schema."},
        )

    @app.exception_handler(EventConflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def bad_request(request, exc):
        return JSONResponse(
            status_code=422, content={"detail": "Request could not pass validation."}
        )

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        logging.getLogger("product_data_platform").error(
            "API failure: %s", type(exc).__name__
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service unavailable. Check initialization and server configuration."
            },
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        return {
            "status": "ready",
            "catalog_revision": catalog.revision(),
            "model_available": settings.model_path.is_file(),
        }

    @app.get("/products")
    def products(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        revision, rows = catalog.snapshot()
        return {
            "revision": revision,
            "total": len(rows),
            "products": rows[offset : offset + limit],
        }

    @app.get("/products/{product_id}")
    def product(product_id: str):
        revision, rows = catalog.snapshot()
        found = next((row for row in rows if row["product_id"] == product_id), None)
        if found is None:
            raise HTTPException(404, "Product not found.")
        return {"revision": revision, "product": found}

    @app.get("/search")
    def search_products(
        q: str = Query(min_length=1, max_length=1000),
        limit: int = Query(5, ge=1, le=50),
        category: str | None = None,
        max_price: float | None = Query(None, ge=0, allow_inf_nan=False),
        in_stock: bool = False,
    ):
        index = search.current()
        return {
            "revision": index.revision,
            "results": index.search(q, limit, category, max_price, in_stock),
        }

    @app.post("/predict")
    def predict_category(payload: PredictionRequest):
        return model().predict(payload.product_name)

    @app.post("/ask")
    def ask(payload: QuestionRequest):
        return answer(payload.question, search, payload.mode, settings)

    @app.post("/events", dependencies=[Depends(require_key)])
    def ingest(event: ProductEvent):
        return apply_event(event, catalog)

    @app.get("/changes")
    def changes(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        rows = catalog.changes(after, limit)
        return {
            "changes": rows,
            "next_cursor": rows[-1]["change_id"] if rows else after,
        }

    @app.get("/monitoring")
    def monitoring():
        fitted = model() if settings.model_path.is_file() else None
        return monitor(catalog, fitted)

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        with lock:
            snapshot = dict(totals)
        return "".join(
            f"platform_{name}_total {value}\n" for name, value in snapshot.items()
        )

    return app


app = create_app()
