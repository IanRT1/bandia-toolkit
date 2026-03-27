"""
automation_service/main.py
--------------------------------
Central webhook entrypoint for all campaigns.
Supports:
- AFTER CALL handlers
- ACTION endpoints
- Clean campaign separation
- Twilio Smart Routing (Salon Ibargo)
"""

from __future__ import annotations

# =========================
# Standard Library Imports
# =========================
import logging
import httpx
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# =========================
# Third-Party Imports
# =========================
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

# =========================
# Campaign: Salon Ibargo
# =========================
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
# NEW: SALON IBARGO SMART ROUTING CONFIG
# ============================================================
PST_ZONE = ZoneInfo("America/Los_Angeles")
BIZ_START = 8
BIZ_END = 23
SALON_GUY_PHONE = "+526865102851"
LK_SIP_URI = "sip:1iyto3q7gfe.sip.livekit.cloud"

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
# NEW: TWILIO SMART ROUTER ENDPOINTS
# ============================================================

@app.post("/twilio-inbound")
async def twilio_smart_router(request: Request):
    """
    Punto de entrada principal para llamadas de Twilio.
    """
    now = datetime.now(tz=PST_ZONE)
    is_biz_hours = BIZ_START <= now.hour < BIZ_END
    
    form_data = await request.form()
    client_number = form_data.get("From", "Unknown")
    call_sid = form_data.get("CallSid", "Unknown")

    logger.info(f"--- ENTRADA --- SID: {call_sid} | De: {client_number} | Horario: {is_biz_hours}")

    if is_biz_hours:
        # El Dial manda al humano, si falla va al action (fallback)
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial timeout="15" callerId="{client_number}" action="/twilio-fallback" method="POST">
                    <Number>{SALON_GUY_PHONE}</Number>
                </Dial>
            </Response>
        """, media_type="application/xml")
    else:
        logger.info(f"Fuera de horario. Mandando a SIP. SID: {call_sid}")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial><Sip>{LK_SIP_URI}</Sip></Dial>
            </Response>
        """, media_type="application/xml")

@app.post("/twilio-fallback")
async def twilio_fallback(request: Request):
    """
    Rescata la llamada si el humano rechaza o no atiende.
    """
    form_data = await request.form()
    status = form_data.get("DialCallStatus")
    bridged = form_data.get("DialBridged") 
    sid = form_data.get("CallSid", "Unknown")
    
    logger.info(f"--- FALLBACK --- SID: {sid} | Status: {status} | Bridged: {bridged}")
    
    if bridged == "false" or status in ["busy", "no-answer", "canceled", "failed"]:
        logger.info(f"Redirigiendo a IA por Bridged={bridged} o Status={status}")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial>
                    <Sip>{LK_SIP_URI}</Sip>
                </Dial>
            </Response>
        """, media_type="application/xml")
    
    return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

# Rutas auxiliares
@app.post("/twilio-whisper")
async def twilio_whisper(request: Request):
    return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Gather numDigits="1" timeout="10" action="/twilio-connect-confirm">
                <Say language="es-MX">Llamada de cliente. Presiona uno para contestar.</Say>
            </Gather>
            <Hangup/>
        </Response>
    """, media_type="application/xml")

@app.post("/twilio-connect-confirm")
async def twilio_connect_confirm(request: Request):
    form_data = await request.form()
    digit = form_data.get("Digits")
    if digit == "1":
        return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
            <Response><Say language="es-MX">Conectando.</Say></Response>
        """, media_type="application/xml")
    return Response(content="""<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>""", media_type="application/xml")

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

@app.post("/salon_ibargo_after_call")
async def salon_ibargo_after_call_route(request: Request):
    return await handle_salon_after_call(request)

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

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("main:app", host=host, port=port, reload=False)
