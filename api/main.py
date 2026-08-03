from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from api.utils.logger import logger, trace_id_var
import uuid
import time
from api.routers import config, ingest

app = FastAPI(title="Smart Dunning API", version="1.0.0")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Middleware that traces HTTP requests and responses.

    Args:
        request (Request): The incoming HTTP request.
        call_next (Callable): The next middleware or route handler.

    Returns:
        Response: The HTTP response with trace ID header.
    """
    trace_id = str(uuid.uuid4())
    trace_id_var.set(trace_id)

    start_time = time.time()
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"Finalized request: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.2f}ms"
    )

    response.headers["X-Trace-ID"] = trace_id
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Payload validation rejected: {exc.errors()}")

    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "message": "The payload doesnt follow the correct schema",
            "trace_id": trace_id_var.get(),
            "details": [
                {
                    "field": " -> ".join([str(loc) for loc in error["loc"]]),
                    "issue": error["msg"],
                }
                for error in exc.errors()
            ],
        },
    )

app.include_router(config.router)
app.include_router(ingest.router)
