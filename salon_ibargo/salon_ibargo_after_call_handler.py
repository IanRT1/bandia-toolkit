import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import csv

from fastapi import Request

from salon_ibargo.salon_ibargo_ai_utils import (
    summarize_transcript,
    transcript_to_single_line,
)
from shared.gsheet_utils import append_row_to_sheet


# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("salon_ibargo_after_call")


# =====================================================
# CONFIG
# =====================================================

PST = ZoneInfo("America/Los_Angeles")
BASE_DIR = Path(__file__).resolve().parent

CALLS_CSV = BASE_DIR / "calls_log.csv"
VISITS_CSV = BASE_DIR / "scheduled_visits.csv"

CALL_HEADERS = [
    "created_at_pst",
    "call_started_at",
    "call_ended_at",
    "call_duration_seconds",
    "transcript",
    "summary",
    "call_id",
]

VISIT_HEADERS = [
    "created_at_pst",
    "name",
    "purpose",
    "visit_date",
    "visit_time",
    "call_id",
]


# =====================================================
# CSV APPEND
# =====================================================

def append_csv(path: Path, headers, row):
    exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)

        if not exists:
            writer.writeheader()

        writer.writerow(row)


# =====================================================
# AFTER CALL HANDLER
# =====================================================

async def handle_salon_after_call(request: Request):

    payload = await request.json()

    # 🔥 Always log raw payload
    logger.info("[handle_salon_after_call] RAW PAYLOAD: %s", payload)

    call_id = payload.get("call_id")

    call_started_at = datetime.strptime(
        payload["call_started_at"],
        "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=PST)

    transcript = payload.get("transcript", [])
    confirmed_visit = payload.get("confirmed_visit")

    call_ended = datetime.now(tz=PST)
    duration = int((call_ended - call_started_at).total_seconds())

    summary = None
    if transcript:
        summary = await summarize_transcript(transcript)

    call_row = {
        "created_at_pst": call_ended.strftime("%Y-%m-%d %H:%M:%S"),
        "call_started_at": call_started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "call_ended_at": call_ended.strftime("%Y-%m-%d %H:%M:%S"),
        "call_duration_seconds": duration,
        "transcript": transcript_to_single_line(transcript),
        "summary": summary,
        "call_id": call_id,
    }

    append_csv(CALLS_CSV, CALL_HEADERS, call_row)

    append_row_to_sheet(
        sheet_name="Llamadas",
        headers=CALL_HEADERS,
        row=call_row,
    )

    if confirmed_visit:

        visit_row = {
            "created_at_pst": call_row["created_at_pst"],
            "name": confirmed_visit["name"],
            "purpose": confirmed_visit["purpose"],
            "visit_date": confirmed_visit["visit_date"],
            "visit_time": confirmed_visit["visit_time"],
            "call_id": call_id,
        }

        append_csv(VISITS_CSV, VISIT_HEADERS, visit_row)

        append_row_to_sheet(
            sheet_name="Citas",
            headers=VISIT_HEADERS,
            row=visit_row,
        )

    logger.info("Salon Ibargo after-call completed call_id=%s", call_id)

    return {"status": "processed"}
