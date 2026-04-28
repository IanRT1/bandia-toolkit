import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request

from vg_consultoria.vg_consultoria_ai_utils import (
    summarize_transcript,
    transcript_to_single_line,
)
from shared.gsheet_utils import append_row_to_sheet

# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("vg_consultoria_after_conversation")

# =====================================================
# CONFIG
# =====================================================

PST = ZoneInfo("America/Los_Angeles")
CAMPAIGN = "vg_consultoria"

# =====================================================
# SHEET HEADERS (MATCH GOOGLE SHEETS EXACTLY)
# =====================================================

CALL_HEADERS = [
    "Creado",
    "From Phone Number",
    "To Phone Number",
    "Empiezo Llamada",
    "Termino Llamada",
    "Duración",
    "Transcripción",
    "Resumen",
    "Grabación",
    "Appointment Requested",
    "ID",
]

# =====================================================
# AFTER CONVERSATION HANDLER
# =====================================================

async def handle_vg_consultoria_after_call(request: Request):
    payload = await request.json()

    logger.info("[handle_vg_consultoria_after_call] RAW PAYLOAD: %s", payload)

    # -------------------------------------------------
    # REQUIRED FIELDS
    # -------------------------------------------------

    conversation_id = payload["conversation_id"]
    started_str = payload["conversation_started_at"]
    ended_str = payload["conversation_ended_at"]

    transcript = payload.get("transcript", [])

    from_phone_number = payload.get("from_phone_number")
    to_phone_number = payload.get("to_phone_number")
    call_sid = payload.get("call_sid")

    confirmed_visit = payload.get("confirmed_visit")
    appointment_requested = bool(confirmed_visit)

    if not to_phone_number:
        to_phone_number = os.environ.get("VG_CONSULTORIA_PHONE_NUMBER")

    # -------------------------------------------------
    # PARSE TIMESTAMPS
    # -------------------------------------------------

    conversation_started_at = datetime.strptime(
        started_str,
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=PST)

    conversation_ended_at = datetime.strptime(
        ended_str,
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=PST)

    duration = int(
        (conversation_ended_at - conversation_started_at).total_seconds()
    )

    # -------------------------------------------------
    # SUMMARIZE TRANSCRIPT
    # -------------------------------------------------

    if transcript:
        summary = await summarize_transcript(transcript)
    else:
        summary = "Llamada Fantasma 👻"

    single_line_transcript = transcript_to_single_line(transcript)

    created_str = conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S")
    started_fmt = conversation_started_at.strftime("%Y-%m-%d %H:%M:%S")
    ended_fmt = conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S")
    appointment_str = "Si" if appointment_requested else "No"

    # -------------------------------------------------
    # BUILD RECORDING URL
    # -------------------------------------------------

    recording_url = (
        f"https://bandia-toolkit-qwt3.onrender.com/recording?call_sid={call_sid}"
        if call_sid
        else None
    )

    # -------------------------------------------------
    # APPEND TO SHEET
    # -------------------------------------------------

    sheet_name = "Llamadas"
    headers = CALL_HEADERS

    row = {
        "Creado": created_str,
        "From Phone Number": from_phone_number,
        "To Phone Number": to_phone_number,
        "Empiezo Llamada": started_fmt,
        "Termino Llamada": ended_fmt,
        "Duración": duration,
        "Transcripción": single_line_transcript,
        "Resumen": summary,
        "Grabación": recording_url,
        "Appointment Requested": appointment_str,
        "ID": conversation_id,
    }

    append_row_to_sheet(
        campaign=CAMPAIGN,
        sheet_name=sheet_name,
        headers=headers,
        row=row,
    )

    logger.info(
        "VG Consultoria after-conversation completed conversation_id=%s",
        conversation_id,
    )

    return {"status": "processed"}