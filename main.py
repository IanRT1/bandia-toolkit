"""
automation_service/main.py
--------------------------------
Central webhook entrypoint for all campaigns.
Supports:
- AFTER CALL handlers
- ACTION endpoints
- Clean campaign separation
"""

from __future__ import annotations

# =========================
# Standard Library Imports
# =========================
import logging
import os

# =========================
# Third-Party Imports
# =========================
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# =========================
# Campaign: Salon Ibargo
# =========================
from salon_ibargo.salon_ibargo_after_call_handler import handle_salon_after_call
from salon_ibargo.salon_ibargo_actions import (
    multiplica_numeros_endpoint,
    agendar_cita_disponibilidad_endpoint,
    cotizar_evento_endpoint,
)

# =========================
# Bootstrap
# =========================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI()


# =========================
# General Health
# =========================

@app.get("/")
async def index():
    return {"status": "ok", "service": "automation_service"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ============================================================
# CAMPAIGN: SALON IBARGO
# ============================================================

# ----------------------------
# AFTER CALL
# ----------------------------

@app.post("/salon-ibargo/after-call")
async def salon_ibargo_after_call_route(request: Request):
    """
    Salon Ibargo – After Call automation
    """
    return await handle_salon_after_call(request)


# ----------------------------
# ACTION: multiplica_numeros
# ----------------------------

@app.post("/salon-ibargo/multiplica-numeros")
async def salon_ibargo_multiplica_numeros_route(request: Request):
    return await multiplica_numeros_endpoint(request)


# ----------------------------
# ACTION: agendar_cita_disponibilidad
# ----------------------------

@app.post("/salon-ibargo/agendar-cita-disponibilidad")
async def salon_ibargo_agendar_cita_route(request: Request):
    return await agendar_cita_disponibilidad_endpoint(request)


# ----------------------------
# ACTION: cotizar_evento
# ----------------------------

@app.post("/salon-ibargo/cotizar-evento")
async def salon_ibargo_cotizar_evento_route(request: Request):
    return await cotizar_evento_endpoint(request)


# ============================================================
# GLOBAL ERROR HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_error_handler(request: Request, e: Exception):
    logger.exception("Unhandled exception during request")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error"},
    )


# ============================================================
# Local Dev Entrypoint
# ============================================================

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))

    logger.info("Starting automation service on http://%s:%s", host, port)

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
    )
