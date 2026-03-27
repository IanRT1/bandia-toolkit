"""
automation_service/main.py - VERSIÓN SIMPLIFICADA
IA solo entra por: No contesta (20s), Ocupado o Fuera de Horario.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI()

PST_ZONE = ZoneInfo("America/Los_Angeles")
BIZ_START = 8
BIZ_END = 23
SALON_GUY_PHONE = "+526865102851"
LK_SIP_URI = "sip:1iyto3q7gfe.sip.livekit.cloud"

@app.post("/twilio-inbound")
async def twilio_smart_router(request: Request):
    now = datetime.now(tz=PST_ZONE)
    is_biz_hours = BIZ_START <= now.hour < BIZ_END
    form_data = await request.form()
    client_number = form_data.get("From", "Unknown")
    
    logger.info(f"--- ENTRADA --- De: {client_number} | Horario: {is_biz_hours}")

    if is_biz_hours:
        # TIMEOUT de 20 segundos antes de pasar a la IA
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial timeout="20" callerId="{client_number}" action="/twilio-fallback" method="POST">
                    <Number>{SALON_GUY_PHONE}</Number>
                </Dial>
            </Response>
        """, media_type="application/xml")
    else:
        # Fuera de horario va directo a Mia
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial><Sip>{LK_SIP_URI}</Sip></Dial>
            </Response>
        """, media_type="application/xml")

@app.post("/twilio-fallback")
async def twilio_fallback(request: Request):
    form_data = await request.form()
    status = form_data.get("DialCallStatus")
    
    logger.info(f"--- FALLBACK --- Status recibido: {status}")
    
    # Lógica solicitada:
    # 1. Si el status es 'no-answer' (pasaron los 20s) o 'busy' -> Entra el bot
    # 2. Si el status es 'completed' (dio decline) o 'canceled' -> Se corta la llamada
    
    if status in ["no-answer", "busy", "failed"]:
        logger.info(f"Transfiriendo a IA Mia por status: {status}")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial><Sip>{LK_SIP_URI}</Sip></Dial>
            </Response>
        """, media_type="application/xml")
    
    # En cualquier otro caso (como 'completed' por decline), colgamos
    logger.info(f"Colgando llamada final. Status fue: {status}")
    return Response(content="""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Hangup/>
        </Response>
    """, media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
