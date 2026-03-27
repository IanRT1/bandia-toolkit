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
SALON_GUY_PHONE = "+526865102851"
LK_SIP_URI = "sip:1iyto3q7gfe.sip.livekit.cloud"

@app.post("/twilio-inbound")
async def twilio_smart_router(request: Request):
    form_data = await request.form()
    client_number = form_data.get("From", "Unknown")
    
    # Bajamos a 12 segundos. Si llega a 20, la red nos cuelga antes de procesar el fallback.
    return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Dial timeout="12" callerId="{client_number}" action="/twilio-fallback" method="POST">
                <Number>{SALON_GUY_PHONE}</Number>
            </Dial>
        </Response>
    """, media_type="application/xml")

@app.post("/twilio-fallback")
async def twilio_fallback(request: Request):
    form_data = await request.form()
    status = form_data.get("DialCallStatus")
    bridged = form_data.get("DialBridged")
    
    logger.info(f"--- FALLBACK --- Status: {status} | Bridged: {bridged}")
    
    # Si no contestó en 12s, Mia entra de inmediato.
    if bridged == "false" or status in ["no-answer", "busy", "failed"]:
        logger.info(f"TRANSFIRIENDO A IA MIA - Status: {status}")
        return Response(content=f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Dial>
                    <Sip>{LK_SIP_URI}</Sip>
                </Dial>
            </Response>
        """, media_type="application/xml")
    
    return Response(content="<Response><Hangup/></Response>", media_type="application/xml")

@app.get("/health")
async def health(): return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
