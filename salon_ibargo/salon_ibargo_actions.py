import logging
from fastapi import Request
from fastapi.responses import JSONResponse

from .salon_ibargo_ai_utils import normalize_visit_datetime_pst


# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("salon_ibargo_actions")


# =====================================================
# ACTION: multiplica_numeros
# =====================================================

async def multiplica_numeros_endpoint(request: Request):

    payload = await request.json()
    logger.info("[multiplica_numeros] RAW PAYLOAD: %s", payload)

    number1 = payload.get("number1")
    number2 = payload.get("number2")

    if number1 is None or number2 is None:
        return JSONResponse(
            {"error": "number1 and number2 are required"},
            status_code=400,
        )

    result = number1 * number2

    return JSONResponse(
        {
            "status": "success",
            "result": result,
            "message": f"The product of {number1} and {number2} is {result}",
        }
    )


# =====================================================
# ACTION: agendar_cita_disponibilidad
# =====================================================

async def agendar_cita_disponibilidad_endpoint(request: Request):

    payload = await request.json()
    logger.info("[agendar_cita_disponibilidad] RAW PAYLOAD: %s", payload)

    name = payload.get("name")
    visit_date = payload.get("visit_date")
    visit_time = payload.get("visit_time")
    purpose = payload.get("purpose")

    if not all([name, visit_date, visit_time, purpose]):
        return JSONResponse(
            {"error": "Missing required fields"},
            status_code=400,
        )

    normalized = await normalize_visit_datetime_pst(
        visit_date=visit_date,
        visit_time=visit_time,
    )

    if normalized.get("confidence") != "high":
        return JSONResponse(
            {"status": "low_confidence"},
            status_code=400,
        )

    visit = {
        "name": name,
        "purpose": purpose,
        "visit_date": normalized["visit_date"],
        "visit_time": normalized["visit_time"],
    }

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


# =====================================================
# ACTION: cotizar_evento
# =====================================================

async def cotizar_evento_endpoint(request: Request):

    payload = await request.json()
    logger.info("[cotizar_evento] RAW PAYLOAD: %s", payload)

    tipo_evento = payload.get("tipo_evento")
    numero_invitados = payload.get("numero_invitados")

    if not tipo_evento or numero_invitados is None:
        return JSONResponse(
            {"error": "tipo_evento and numero_invitados are required"},
            status_code=400,
        )

    base_price = 5000
    price_per_guest = 350

    cotizacion = base_price + (numero_invitados * price_per_guest)

    tipo = tipo_evento.lower()

    if tipo in {"boda", "wedding"}:
        cotizacion *= 1.2
    elif tipo in {"conferencia", "corporativo"}:
        cotizacion *= 1.1

    cotizacion = int(cotizacion)

    return JSONResponse(
        {
            "status": "success",
            "estimated_price_mxn": cotizacion,
            "message": (
                f"Para un {tipo_evento} con aproximadamente {numero_invitados} invitados, "
                f"la cotización estimada es de {cotizacion} MXN."
            ),
        }
    )
