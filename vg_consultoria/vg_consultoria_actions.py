import logging
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from .vg_consultoria_ai_utils import normalize_visit_datetime_pst
from shared.google_calendar import is_slot_available


# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("vg_consultoria_actions")


# =====================================================
# CONFIG (easily tweakable)
# =====================================================

CAMPAIGN = "vg_consultoria"
APPOINTMENT_DURATION_MINUTES = 60
BUSINESS_HOUR_START = 9   # 9:00 AM (inclusive)
BUSINESS_HOUR_END = 16    # 4:00 PM (last appointment must START before this)


# =====================================================
# BASE FIELD VALIDATION
# =====================================================

def extract_base_fields(payload: dict):
    conversation_id = payload.get("conversation_id")
    channel = payload.get("channel")

    if not conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required",
        )

    if not channel:
        raise HTTPException(
            status_code=400,
            detail="channel is required",
        )

    return conversation_id, channel


# =====================================================
# BUSINESS HOURS CHECK
# =====================================================

def _is_within_business_hours(visit_date: str, visit_time: str) -> bool:
    """
    Returns True if visit_time falls within [BUSINESS_HOUR_START, BUSINESS_HOUR_END).
    Last valid start is one hour before END so the appointment fits in the day.
    """
    dt = datetime.strptime(f"{visit_date} {visit_time}", "%Y-%m-%d %H:%M")
    return BUSINESS_HOUR_START <= dt.hour < BUSINESS_HOUR_END


# =====================================================
# ACTION: agendar_cita_disponibilidad
# =====================================================

async def agendar_cita_disponibilidad_endpoint(request: Request):

    payload = await request.json()
    logger.info("[agendar_cita_disponibilidad] RAW PAYLOAD: %s", payload)

    conversation_id, channel = extract_base_fields(payload)

    name = payload.get("name")
    visit_date = payload.get("visit_date")
    visit_time = payload.get("visit_time")
    purpose = payload.get("purpose")  # optional

    if not all([name, visit_date, visit_time]):
        raise HTTPException(
            status_code=400,
            detail="name, visit_date, and visit_time are required",
        )

    # ---------------------------------------------------------
    # 1. Normalize fuzzy date/time
    # ---------------------------------------------------------
    normalized = await normalize_visit_datetime_pst(
        visit_date=visit_date,
        visit_time=visit_time,
    )

    if normalized.get("confidence") != "high":
        logger.info("Visit date/time could not be confidently normalized")
        return JSONResponse(
            {
                "status": "rejected",
                "reason": "ambiguous_datetime",
                "message": (
                    "No pude entender la fecha u hora con certeza. "
                    "Podrias repetirme exactamente que dia y a que hora te gustaria?"
                ),
            },
            status_code=200,
        )

    norm_date = normalized["visit_date"]
    norm_time = normalized["visit_time"]

    # ---------------------------------------------------------
    # 2. Business hours check
    # ---------------------------------------------------------
    if not _is_within_business_hours(norm_date, norm_time):
        logger.info(
            "Outside business hours visit_date=%s visit_time=%s",
            norm_date,
            norm_time,
        )
        return JSONResponse(
            {
                "status": "rejected",
                "reason": "outside_business_hours",
                "message": (
                    f"Lo siento, nuestro horario de atencion es de "
                    f"{BUSINESS_HOUR_START}:00 a {BUSINESS_HOUR_END}:00. "
                    f"Te gustaria agendar dentro de ese horario?"
                ),
            },
            status_code=200,
        )

    # ---------------------------------------------------------
    # 3. Google Calendar availability check
    # ---------------------------------------------------------
    try:
        availability = await is_slot_available(
            campaign=CAMPAIGN,
            visit_date=norm_date,
            visit_time=norm_time,
            duration_minutes=APPOINTMENT_DURATION_MINUTES,
        )
    except Exception:
        logger.exception("Calendar availability check failed")
        return JSONResponse(
            {
                "status": "rejected",
                "reason": "calendar_check_failed",
                "message": (
                    "No pude verificar la disponibilidad en este momento. "
                    "Podrias intentarlo de nuevo en un momento?"
                ),
            },
            status_code=200,
        )

    if not availability["available"]:
        logger.info(
            "Slot unavailable visit_date=%s visit_time=%s conflicts=%d",
            norm_date,
            norm_time,
            len(availability["conflicts"]),
        )
        return JSONResponse(
            {
                "status": "rejected",
                "reason": "slot_unavailable",
                "message": "Esa hora ya esta ocupada. Te gustaria proponer otro horario?",
            },
            status_code=200,
        )

    # ---------------------------------------------------------
    # 4. Confirm
    # ---------------------------------------------------------
    visit = {
        "name": name,
        "purpose": purpose,
        "visit_date": norm_date,
        "visit_time": norm_time,
    }

    logger.info(
        "agendar_cita | conversation_id=%s channel=%s visit=%s",
        conversation_id,
        channel,
        visit,
    )

    return JSONResponse(
        {
            "status": "confirmed",
            "confirmed_visit": visit,
            "message": (
                f"Perfecto {name}. Tu visita quedo agendada para el "
                f"{visit['visit_date']} a las {visit['visit_time']}."
            ),
        }
    )