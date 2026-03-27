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
import httpx
import os

# =========================
# Third-Party Imports
# =========================
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# =========================
# Campaign: Salon Ibargo
# =========================
from salon_ibargo.salon_ibargo_after_call_handler import handle_salon_after_call
from salon_ibargo.salon_ibargo_actions import (
    agendar_cita_disponibilidad_endpoint,
    cotizar_evento_endpoint,
)
from salon_ibargo.salon_ibargo_call_routing import (
    salon_ibargo_inbound_call,
    screen_call,
    screen_result,
    dial_action,
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


# ----------------------------
# RECORDING PROXY
# ----------------------------

@app.get("/recording")
async def get_recording(call_sid: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    lookup_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}/Recordings.json"

    async with httpx.AsyncClient() as client:
        lookup = await client.get(lookup_url, auth=(account_sid, auth_token))

    recordings = lookup.json().get("recordings", [])
    if not recordings:
        return JSONResponse(status_code=404, content={"error": "recording_not_found"})

    recording_sid = recordings[0]["sid"]
    mp3_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{recording_sid}.mp3"

    async with httpx.AsyncClient() as client:
        response = await client.get(mp3_url, auth=(account_sid, auth_token))

    if response.status_code != 200:
        return JSONResponse(status_code=404, content={"error": "recording_not_found"})

    return StreamingResponse(
        iter([response.content]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename={call_sid}.mp3"}
    )


# ============================================================
# CAMPAIGN: SALON IBARGO
# ============================================================

# ----------------------------
# INBOUND CALL
# ----------------------------

@app.post("/salon_ibargo/inbound_call")
async def salon_ibargo_inbound_call_route(request: Request):
    return await salon_ibargo_inbound_call(request)

@app.post("/salon_ibargo/call/screen")
async def salon_ibargo_screen_route(request: Request):
    return await screen_call(request)

@app.post("/salon_ibargo/call/screen_result")
async def salon_ibargo_screen_result_route(request: Request):
    return await screen_result(request)

@app.post("/salon_ibargo/call/dial_action")
async def salon_ibargo_dial_action_route(request: Request):
    return await dial_action(request)

# ----------------------------
# AFTER CALL
# ----------------------------

@app.post("/salon_ibargo_after_call")
async def salon_ibargo_after_call_route(request: Request):
    return await handle_salon_after_call(request)


# ----------------------------
# ACTIONS
# ----------------------------

@app.post("/salon_ibargo_agendar_cita_disponibilidad")
async def salon_ibargo_agendar_cita_route(request: Request):
    return await agendar_cita_disponibilidad_endpoint(request)


@app.post("/salon_ibargo_cotizar_evento")
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