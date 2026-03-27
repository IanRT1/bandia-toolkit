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
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

# =========================
# Third-Party Imports
# =========================
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

# =========================
# Campaign: Salon Ibargo
# =========================
from salon_ibargo.salon_ibargo_call_routing import salon_ibargo_inbound_call
from salon_ibargo.salon_ibargo_after_call_handler import handle_salon_after_call
from salon_ibargo.salon_ibargo_actions import (
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

# ============================================================
# SALON IBARGO - VOICE ROUTING CONFIG
# ============================================================

BUSINESS_TZ = ZoneInfo("America/Tijuana")

SALON_AGENT_SIP_URI = os.getenv(
    "SALON_AGENT_SIP_URI",
    "sip:1iyto3q7gfe.sip.livekit.cloud",
)

CARLOS_NUMBER = os.getenv("CARLOS_NUMBER", "+526862887006")

SALON_BUSINESS_HOURS_START = int(os.getenv("SALON_BUSINESS_HOURS_START", "7"))
SALON_BUSINESS_HOURS_END = int(os.getenv("SALON_BUSINESS_HOURS_END", "23"))

# Ojo: Twilio suele agregar unos segundos extra reales al timeout de <Dial>.
# Si quieres aprox 12 segundos reales, 7 suele ser buena base.
CARLOS_RING_TIMEOUT = int(os.getenv("CARLOS_RING_TIMEOUT", "7"))

# Tiempo para que Carlos presione 1 o 2 después de contestar
CARLOS_SCREEN_TIMEOUT = int(os.getenv("CARLOS_SCREEN_TIMEOUT", "10"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# =========================
# Helpers
# =========================

def get_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")

    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    return str(request.base_url).rstrip("/")


def is_salon_business_hours() -> bool:
    now = datetime.now(BUSINESS_TZ)
    return SALON_BUSINESS_HOURS_START <= now.hour < SALON_BUSINESS_HOURS_END


def build_agent_twiml() -> str:
    vr = VoiceResponse()
    dial = vr.dial(answer_on_bridge=True)
    dial.sip(SALON_AGENT_SIP_URI)
    return str(vr)


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