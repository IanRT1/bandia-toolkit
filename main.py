from __future__ import annotations
import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI()

SALON_GUY_PHONE = "+526865102851"
LK_SIP_URI = "sip:1iyto3q7gfe.sip.livekit.cloud"

@app.post("/twilio-inbound")
async def twilio_smart_router(request: Request):
    form_data = await request.form()
    client_number = form_data.get("From", "Unknown")
    
    # Timeout de 13 segundos: tiempo suficiente para 3 timbres, 
    # pero antes de que la red celular de México fuerce su propio buzón.
    return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Dial timeout="13" callerId="{client_number}" action="/twilio-fallback" method="POST">
                <Number>{SALON_GUY_PHONE}</Number>
            </Dial>
        </Response>
    """, media_type="application/xml")

@app.post("/twilio-fallback")
async def twilio_fallback(request: Request):
    form_data = await request.form()
    status = form_data.get("DialCallStatus")
    bridged = str(form_data.get("DialBridged", "false")).lower()
    
    logger.info(f"--- FALLBACK --- Status: {status} | Bridged: {bridged}")
    
    # Si NO se conectó con el humano (bridged == false) 
    # o el status indica que no hubo respuesta/error.
    if bridged == "false" or status in ["no-answer", "busy", "failed"]:
        logger.info(f"EJECUTANDO RESCATE: Transfiriendo a IA Mia (Status: {status})")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say language="es-MX">Conectando con un agente.</Say>
                <Dial>
                    <Sip>{LK_SIP_URI}</Sip>
                </Dial>
            </Response>
        """, media_type="application/xml")
    
    # Si bridged es true, significa que tu primo sí contestó y ya terminaron de hablar.
    return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
