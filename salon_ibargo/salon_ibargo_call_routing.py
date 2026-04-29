"""
salon_ibargo/salon_ibargo_call_routing.py
--------------------------------
Inbound call routing logic for Salon Ibargo
Handles:
- Business hours routing
- Human screening
- AI fallback
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse


logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================

BUSINESS_TZ = ZoneInfo("America/Tijuana")

AGENT_SIP_URI = os.getenv("SALON_IBARGO_SIP_URI")

FORWARD_NUMBER = os.getenv("SALON_IBARGO_FORWARD_NUMBER")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

RING_TIMEOUT_SECONDS = 7
SCREEN_TIMEOUT_SECONDS = 10

#BUSINESS_HOURS_START = 9
#BUSINESS_HOURS_END = 17

TEST_BYPASS_NUMBER = "+526862887006"


# =========================
# Helpers
# =========================

def get_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")

    if proto and host:
        return f"{proto}://{host}"

    return str(request.base_url).rstrip("/")


def is_business_hours() -> bool:
    now = datetime.now(BUSINESS_TZ)
    weekday = now.weekday()  # lunes=0, domingo=6
    hour = now.hour

    # Lunes a viernes: 9 AM a 5 PM
    if 0 <= weekday <= 4:
        return 9 <= hour < 17

    # Sábado: 9 AM a 1 PM
    if weekday == 5:
        return 9 <= hour < 13

    # Domingo: cerrado
    return False


def build_agent_twiml() -> str:
    vr = VoiceResponse()
    dial = vr.dial(answer_on_bridge=True)
    dial.sip(AGENT_SIP_URI)
    return str(vr)


# =========================
# ENTRYPOINT
# =========================

async def salon_ibargo_inbound_call(request: Request):
    form = await request.form()

    base_url = get_base_url(request)
    from_number = form.get("From")
    call_sid = form.get("CallSid")

    logger.info(
        "Inbound call | from=%s | call_sid=%s | business_hours=%s",
        from_number,
        call_sid,
        is_business_hours(),
    )

    vr = VoiceResponse()

    # Hardcoded test number -> direct to AI
    if from_number == TEST_BYPASS_NUMBER:
        logger.info("Test bypass number detected -> direct to AI")
        dial = vr.dial(answer_on_bridge=True)
        dial.sip(AGENT_SIP_URI)
        return Response(str(vr), media_type="application/xml")

    # Outside business hours -> AI
    if not is_business_hours():
        dial = vr.dial(answer_on_bridge=True)
        dial.sip(AGENT_SIP_URI)
        return Response(str(vr), media_type="application/xml")

    # Inside business hours -> human first
    dial_action_url = f"{base_url}/salon_ibargo/call/dial_action"

    screen_url = f"{base_url}/salon_ibargo/call/screen?" + urlencode({
        "parent_call_sid": call_sid or "",
        "caller_number": from_number or "",
    })

    dial = vr.dial(
        answer_on_bridge=True,
        action=dial_action_url,
        method="POST",
        timeout=RING_TIMEOUT_SECONDS,
    )

    dial.number(FORWARD_NUMBER, url=screen_url)

    return Response(str(vr), media_type="application/xml")


# =========================
# SCREENING FLOW
# =========================

async def screen_call(request: Request):
    base_url = get_base_url(request)

    parent_call_sid = request.query_params.get("parent_call_sid", "")
    caller_number = request.query_params.get("caller_number", "")

    result_url = f"{base_url}/salon_ibargo/call/screen_result?" + urlencode({
        "parent_call_sid": parent_call_sid,
        "caller_number": caller_number,
    })

    vr = VoiceResponse()

    gather = vr.gather(
        num_digits=1,
        timeout=SCREEN_TIMEOUT_SECONDS,
        action=result_url,
        method="POST",
        action_on_empty_result=True,
    )

    gather.say(
        "Llamada entrante. Presione 1 para contestar. Presione 2 para enviar al agente.",
        language="es-MX",
    )

    return Response(str(vr), media_type="application/xml")


async def screen_result(request: Request):
    form = await request.form()

    digits = (form.get("Digits") or "").strip()
    parent_call_sid = request.query_params.get("parent_call_sid", "")

    vr = VoiceResponse()

    if digits == "1":
        vr.say("Conectando llamada.", language="es-MX")
        return Response(str(vr), media_type="application/xml")

    if parent_call_sid:
        twilio_client.calls(parent_call_sid).update(
            twiml=build_agent_twiml()
        )

    vr.say("Enviando al agente.", language="es-MX")
    vr.hangup()

    return Response(str(vr), media_type="application/xml")


async def dial_action(request: Request):
    form = await request.form()

    status = (form.get("DialCallStatus") or "").lower()
    bridged = (form.get("DialBridged") or "").lower()

    vr = VoiceResponse()

    if status == "completed" or bridged == "true":
        vr.hangup()
        return Response(str(vr), media_type="application/xml")

    if status in {"no-answer", "busy", "failed"}:
        dial = vr.dial(answer_on_bridge=True)
        dial.sip(AGENT_SIP_URI)
        return Response(str(vr), media_type="application/xml")

    vr.hangup()
    return Response(str(vr), media_type="application/xml")
