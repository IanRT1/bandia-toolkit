import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request

from salon_ibargo.salon_ibargo_ai_utils import (
    summarize_transcript,
    transcript_to_single_line,
)
from shared.gsheet_utils import append_row_to_sheet


# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("salon_ibargo_after_conversation")


# =====================================================
# CONFIG
# =====================================================

PST = ZoneInfo("America/Los_Angeles")


# =====================================================
# SHEET HEADERS (MATCH GOOGLE SHEETS EXACTLY)
# =====================================================

CHAT_HEADERS = [
    "Creado",
    "Empiezo Chat",
    "Termino Chat",
    "Duración",
    "Transcripción",
    "Resumen",
    "ID",
]

CALL_HEADERS = [
    "Creado",
    "Empiezo Llamada",
    "Termino Llamada",
    "Duración",
    "Transcripción",
    "Resumen",
    "ID",
]

VISIT_HEADERS = [
    "Creado",
    "Nombre",
    "Motivo",
    "Fecha",
    "Hora",
    "ID Conversación",
    "Canal",
]


# =====================================================
# AFTER CONVERSATION HANDLER
# =====================================================

async def handle_salon_after_call(request: Request):

    payload = await request.json()

    logger.info("[handle_salon_after_call] RAW PAYLOAD: %s", payload)

    # -------------------------------------------------
    # REQUIRED FIELDS
    # -------------------------------------------------

    conversation_id = payload["conversation_id"]
    channel = payload["channel"]  # "voice" or "chat"
    started_str = payload["conversation_started_at"]
    ended_str = payload["conversation_ended_at"]

    transcript = payload.get("transcript", [])
    confirmed_visit = payload.get("confirmed_visit")

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

    summary = None
    if transcript:
        summary = await summarize_transcript(transcript)

    single_line_transcript = transcript_to_single_line(transcript)

    created_str = conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S")
    started_fmt = conversation_started_at.strftime("%Y-%m-%d %H:%M:%S")
    ended_fmt = conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S")

    # =====================================================
    # ROUTE TO CORRECT CONVERSATION SHEET
    # =====================================================

    if channel == "voice":

        sheet_name = "Llamadas"
        headers = CALL_HEADERS

        row = {
            "Creado": created_str,
            "Empiezo Llamada": started_fmt,
            "Termino Llamada": ended_fmt,
            "Duración": duration,
            "Transcripción": single_line_transcript,
            "Resumen": summary,
            "ID": conversation_id,
        }

    elif channel == "chat":

        sheet_name = "Chats"
        headers = CHAT_HEADERS

        row = {
            "Creado": created_str,
            "Empiezo Chat": started_fmt,
            "Termino Chat": ended_fmt,
            "Duración": duration,
            "Transcripción": single_line_transcript,
            "Resumen": summary,
            "ID": conversation_id,
        }

    else:
        logger.warning(
            "Unknown channel '%s', defaulting to Chats sheet",
            channel,
        )

        sheet_name = "Chats"
        headers = CHAT_HEADERS

        row = {
            "Creado": created_str,
            "Empiezo Chat": started_fmt,
            "Termino Chat": ended_fmt,
            "Duración": duration,
            "Transcripción": single_line_transcript,
            "Resumen": summary,
            "ID": conversation_id,
        }

    append_row_to_sheet(
        sheet_name=sheet_name,
        headers=headers,
        row=row,
    )

    # =====================================================
    # HANDLE CONFIRMED VISIT (ALWAYS GOES TO CITAS)
    # =====================================================

    if confirmed_visit:

        visit_row = {
            "Creado": created_str,
            "Nombre": confirmed_visit["name"],
            "Motivo": confirmed_visit["purpose"],
            "Fecha": confirmed_visit["visit_date"],
            "Hora": confirmed_visit["visit_time"],
            "ID Conversación": conversation_id,
        }

        append_row_to_sheet(
            sheet_name="Citas",
            headers=VISIT_HEADERS,
            row=visit_row,
        )

    logger.info(
        "Salon Ibargo after-conversation completed conversation_id=%s channel=%s",
        conversation_id,
        channel,
    )

    return {"status": "processed"}
