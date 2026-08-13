"""FastAPI Server Entry Point.

Initializes FastAPI application instance, CORS middleware, and includes API routers.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.endpoints import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("main")

app = FastAPI(
    title="AI Clinical Documentation Assistant API",
    description="Multi-agent AI clinical documentation system with human-in-the-loop EHR workflow.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration for Streamlit frontend (http://localhost:8501)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits browser requests from Streamlit UI
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 API endpoints router
app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for container / service monitoring."""
    return {"status": "HEALTHY", "service": "AI Clinical Documentation Assistant API"}
