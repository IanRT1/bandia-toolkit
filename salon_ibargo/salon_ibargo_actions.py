import logging
from fastapi import Request
from fastapi.responses import JSONResponse

from ai_utils import normalize_visit_datetime_pst

logger = logging.getLogger("salon_ibargo_actions")


async def multiplica_numeros_endpoint(request: Request):
    payload = await request.json()
    number1 = payload["number1"]
    number2 = payload["number2"]

    result = number1 * number2

    return JSONResponse({
        "result": f"The product of {number1} and {number2} is {result}"
    })


async def agendar_cita_disponibilidad_endpoint(request: Request):
    payload = await request.json()

    name = payload["name"]
    visit_date = payload["visit_date"]
    visit_time = payload["visit_time"]
    purpose = payload["purpose"]

    normalized = await normalize_visit_datetime_pst(
        visit_date=visit_date,
        visit_time=visit_time,
    )

    if normalized.get("confidence") != "high":
        return JSONResponse({"status": "low_confidence"}, status_code=400)

    visit = {
        "name": name,
        "purpose": purpose,
        "visit_date": normalized["visit_date"],
        "visit_time": normalized["visit_time"],
    }

    return JSONResponse({
        "status": "confirmed",
        "visit": visit,
        "message": (
            f"Perfecto {name}. Tu visita quedó agendada para el "
            f"{visit['visit_date']} a las {visit['visit_time']}."
        )
    })


async def cotizar_evento_endpoint(request: Request):
    payload = await request.json()

    tipo_evento = payload["tipo_evento"]
    numero_invitados = payload["numero_invitados"]

    base_price = 5000
    price_per_guest = 350

    cotizacion = base_price + (numero_invitados * price_per_guest)

    tipo = tipo_evento.lower()

    if tipo in {"boda", "wedding"}:
        cotizacion *= 1.2
    elif tipo in {"conferencia", "corporativo"}:
        cotizacion *= 1.1

    cotizacion = int(cotizacion)

    return JSONResponse({
        "message": (
            f"Para un {tipo_evento} con aproximadamente {numero_invitados} invitados, "
            f"la cotización estimada es de {cotizacion} MXN."
        )
    })
