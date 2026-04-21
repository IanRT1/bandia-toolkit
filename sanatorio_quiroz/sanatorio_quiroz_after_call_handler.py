import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request

from sanatorio_quiroz.sanatorio_quiroz_ai_utils import (
    summarize_transcript,
    transcript_to_single_line,
)
from shared.gsheet_utils import append_row_to_sheet

# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("sanatorio_quiroz_after_conversation")

# =====================================================
# CONFIG
# =====================================================

PST = ZoneInfo("America/Los_Angeles")
CAMPAIGN = "sanatorio_quiroz"

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
    "Callback Requested",
    "ID",
]

# =====================================================
# AFTER CONVERSATION HANDLER
# =====================================================

async def handle_sanatorio_quiroz_after_call(request: Request):
    payload = await request.json()

    logger.info("[handle_sanatorio_quiroz_after_call] RAW PAYLOAD: %s", payload)

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
    callback_requested = payload.get("callback_requested", False)

    if not to_phone_number:
        to_phone_number = os.environ.get("SANATORIO_QUIROZ_PHONE_NUMBER")

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
    callback_str = "Si" if callback_requested else "No"

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
        "Callback Requested": callback_str,
        "ID": conversation_id,
    }

    append_row_to_sheet(
        campaign=CAMPAIGN,
        sheet_name=sheet_name,
        headers=headers,
        row=row,
    )

    logger.info(
        "Sanatorio Quiroz after-conversation completed conversation_id=%s",
        conversation_id,
    )

    return {"status": "processed"}