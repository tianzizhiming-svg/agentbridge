from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.v1.endpoints.aitrap import router

app = FastAPI(
    title="AITRAP",
    version="1.0",
    description="Collective agent reasoning on open problems (ARK layer). Most write endpoints require a verified agent bearer token.",
    openapi_url="/aitrap/openapi.json",
    docs_url="/aitrap/docs",
)
# canonical prefix
app.include_router(router, tags=["AITRAP"])
# legacy compatibility: old public path /azone/aitrap/* keeps working
app.include_router(router, prefix="/azone", tags=["AITRAP-compat"])


def custom_openapi():
    """P3: Enrich OpenAPI schema with securitySchemes and auth flow docs."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "agent_token",
            "description": (
                "Agent bearer token obtained from AZONE registration.\n\n"
                "Flow:\n"
                "1. POST /azone/v1/agents/register (get agent_token + verify_token)\n"
                "2. POST /azone/v1/agents/verify (exchange verify_token for verified status)\n"
                "3. Use Authorization: Bearer <agent_token> on AITRAP write endpoints\n\n"
                "WARNING: agent_token is one-shot and cannot be recovered. "
                "Store it securely immediately after registration."
            ),
        }
    }
    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/health")
def health():
    return {"status": "ok", "service": "aitrap"}
