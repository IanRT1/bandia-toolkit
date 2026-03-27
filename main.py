"""
automation_service/main.py
--------------------------------
Versión Final Optimizada: Control de errores de red y rescate de IA.
"""

from __future__ import annotations

import logging
import httpx
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

# =========================
# Configuración y Logs
# =========================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

PST_ZONE = ZoneInfo("America/Los_Angeles")
BIZ_START = 8
BIZ_END = 23
SALON_GUY_PHONE = "+526865102851"
LK_SIP_URI = "sip:1iyto3q7gfe.sip.livekit.cloud"

# =========================
# Rutas de Twilio
# =========================

@app.post("/twilio-inbound")
async def twilio_smart_router(request: Request):
    """
    Punto de entrada. Intenta conectar con el humano primero.
    Timeout de 15s para ganar a los retardos de red y evitar el buzón.
    """
    now = datetime.now(tz=PST_ZONE)
    is_biz_hours = BIZ_START <= now.hour < BIZ_END
    
    form_data = await request.form()
    client_number = form_data.get("From", "Unknown")
    call_sid = form_data.get("CallSid", "Unknown")

    logger.info(f"--- ENTRADA --- SID: {call_sid} | De: {client_number} | Horario: {is_biz_hours}")

    if is_biz_hours:
        # El action se dispara si no hay respuesta en 15 segundos
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial timeout="15" callerId="{client_number}" action="/twilio-fallback" method="POST">
                    <Number>{SALON_GUY_PHONE}</Number>
                </Dial>
            </Response>
        """, media_type="application/xml")
    else:
        logger.info(f"Fuera de horario. Directo a SIP. SID: {call_sid}")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial><Sip>{LK_SIP_URI}</Sip></Dial>
            </Response>
        """, media_type="application/xml")

@app.post("/twilio-fallback")
async def twilio_fallback(request: Request):
    """
    Lógica de rescate: Solo entra si el humano NO contestó.
    Si el humano dio 'Decline' (Status: completed), se cuelga para evitar buzón.
    """
    form_data = await request.form()
    status = form_data.get("DialCallStatus")
    bridged = form_data.get("DialBridged") # 'true' si hubo conexión real
    sid = form_data.get("CallSid", "Unknown")
    
    logger.info(f"--- FALLBACK --- SID: {sid} | Status: {status} | Bridged: {bridged}")
    
    # 1. Si no contestó (no-answer) tras 15s o estaba ocupado (busy) -> MIA rescata.
    if status in ["no-answer", "busy", "failed"] or (status == "completed" and bridged == "false"):
        logger.info(f"Transfiriendo a IA Mia. Motivo: {status} (Bridged: {bridged})")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial><Sip>{LK_SIP_URI}</Sip></Dial>
            </Response>
        """, media_type="application/xml")
    
    # 2. Si dio Decline o se completó la llamada correctamente, terminamos.
    logger.info(f"Finalizando flujo. Status: {status}")
    return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

# =========================
# Endpoints de Campaña
# =========================

@app.get("/health")
async def health(): return {"status": "healthy"}

@app.post("/salon_ibargo_after_call")
async def salon_after_call(request: Request):
    return await handle_salon_after_call(request)

@app.post("/salon_ibargo_agendar_cita_disponibilidad")
async def salon_agendar(request: Request):
    return await agendar_cita_disponibilidad_endpoint(request)

@app.post("/salon_ibargo_cotizar_evento")
async def salon_cotizar(request: Request):
    return await cotizar_evento_endpoint(request)

@app.get("/recording")
async def get_recording(call_sid: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}/Recordings.json"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, auth=(account_sid, auth_token))
        recs = r.json().get("recordings", [])
        if not recs: return JSONResponse(status_code=404, content={"error": "not_found"})
        mp3 = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{recs[0]['sid']}.mp3"
        res = await client.get(mp3, auth=(account_sid, auth_token))
        return StreamingResponse(iter([res.content]), media_type="audio/mpeg")

@app.exception_handler(Exception)
async def error_handler(request: Request, e: Exception):
    logger.exception("Error interno en el servidor")
    return JSONResponse(status_code=500, content={"error": "internal_error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
