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


CONVERSATION_HEADERS = [
    "created_at_pst",
    "channel",
    "conversation_started_at",
    "conversation_ended_at",
    "duration_seconds",
    "transcript",
    "summary",
    "conversation_id",
]

VISIT_HEADERS = [
    "created_at_pst",
    "name",
    "purpose",
    "visit_date",
    "visit_time",
    "conversation_id",
    "channel",
]


# =====================================================
# AFTER CONVERSATION HANDLER
# =====================================================

async def handle_salon_after_call(request: Request):

    payload = await request.json()

    logger.info("[handle_salon_after_call] RAW PAYLOAD: %s", payload)

    # Required fields
    conversation_id = payload["conversation_id"]
    channel = payload["channel"]  # expected: "voice" or "chat"
    started_str = payload["conversation_started_at"]
    ended_str = payload["conversation_ended_at"]

    transcript = payload.get("transcript", [])
    confirmed_visit = payload.get("confirmed_visit")

    # Parse timestamps
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

    # Summarize transcript
    summary = None
    if transcript:
        summary = await summarize_transcript(transcript)

    # Build conversation row
    conversation_row = {
        "created_at_pst": conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "conversation_started_at": conversation_started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "conversation_ended_at": conversation_ended_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration,
        "transcript": transcript_to_single_line(transcript),
        "summary": summary,
        "conversation_id": conversation_id,
    }

    # =====================================================
    # ROUTE TO CORRECT SHEET
    # =====================================================

    if channel == "voice":
        sheet_name = "Llamadas"
    elif channel == "chat":
        sheet_name = "Chats"
    else:
        # Defensive default
        sheet_name = "Chats"
        logger.warning(
            "Unknown channel '%s', defaulting to Chats sheet",
            channel,
        )

    append_row_to_sheet(
        sheet_name=sheet_name,
        headers=CONVERSATION_HEADERS,
        row=conversation_row,
    )

    # =====================================================
    # HANDLE CONFIRMED VISIT (ALWAYS GOES TO CITAS)
    # =====================================================

    if confirmed_visit:

        visit_row = {
            "created_at_pst": conversation_row["created_at_pst"],
            "name": confirmed_visit["name"],
            "purpose": confirmed_visit["purpose"],
            "visit_date": confirmed_visit["visit_date"],
            "visit_time": confirmed_visit["visit_time"],
            "conversation_id": conversation_id,
            "channel": channel,
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
