import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from .vg_consultoria_ai_utils import normalize_visit_datetime_pst


# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("vg_consultoria_actions")


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

    normalized = await normalize_visit_datetime_pst(
        visit_date=visit_date,
        visit_time=visit_time,
    )

    if normalized.get("confidence") != "high":
        logger.info("Visit date/time could not be confidently normalized")
        raise HTTPException(
            status_code=400,
            detail="Visit date/time could not be confidently normalized",
        )

    visit = {
        "name": name,
        "purpose": purpose,
        "visit_date": normalized["visit_date"],
        "visit_time": normalized["visit_time"],
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
                f"Perfecto {name}. Tu visita quedó agendada para el "
                f"{visit['visit_date']} a las {visit['visit_time']}."
            ),
        }
    )