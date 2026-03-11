# ai_utils.py

from typing import List
import os
import logging

from dotenv import load_dotenv
from pydantic import BaseModel
from openai import AsyncOpenAI

import json
from datetime import datetime
from zoneinfo import ZoneInfo

PST = ZoneInfo("America/Los_Angeles")


# -------------------------------------------------
# Environment
# -------------------------------------------------

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

# -------------------------------------------------
# OpenAI client (OFFICIAL SDK)
# -------------------------------------------------

client = AsyncOpenAI(api_key=OPENAI_API_KEY, max_retries=0)

SUM_MODEL = "gpt-5-nano"
STD_MODEL = "gpt-5-mini"

# -------------------------------------------------
# Logging (minimal)
# -------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_utils")

# -------------------------------------------------
# Models
# -------------------------------------------------

class TranscriptItem(BaseModel):
    role: str
    content: str

# -------------------------------------------------
# Helpers
# -------------------------------------------------

def transcript_to_single_line(transcript: list[dict]) -> str:
    return " | ".join(
        f"{item['role'].upper()}: {item['content'].replace('\n', ' ').strip()}"
        for item in transcript
        if item.get("content")
    )


# -------------------------------------------------
# Public API
# -------------------------------------------------

async def summarize_transcript(transcript: List[TranscriptItem], channel: str = "voice") -> str:

    if channel == "voice":
        medium = "llamada telefónica"
        ghost_label = "Llamada Fantasma 👻"
    elif channel == "chat":
        medium = "conversación de chat"
        ghost_label = "Chat Fantasma 👻"
    else:
        medium = "conversación"
        ghost_label = "Fantasma 👻"

    transcript_dicts = [
        item if isinstance(item, dict) else vars(item)
        for item in transcript
    ]

    user_turns = [item for item in transcript_dicts if item.get("role") == "user"]
    user_content = " ".join(
        item.get("content", "") or "" for item in user_turns
    ).strip()

    if not user_content or len(user_content) < 10:
        logger.info("summarize_transcript: ghost detected (no user input) channel=%s", channel)
        return ghost_label

    transcript_text = transcript_to_single_line(transcript)

    prompt = (
        f"Resume la siguiente {medium} en UN SOLO PÁRRAFO breve. "
        "No uses listas ni encabezados. "
        "Describe la intención del cliente y cómo terminó la conversación.\n\n"
        f"Si el cliente nunca dijo nada coherente o la {medium} fue silenciosa, "
        f"responde ÚNICAMENTE con: '{ghost_label}'. No agregar nada extra.\n\n"
        f"{transcript_text}"
    )

    logger.info("summarize_transcript: calling %s channel=%s", SUM_MODEL, channel)

    try:
        response = await client.chat.completions.create(
            model=SUM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=10.0,
        )
        result = response.choices[0].message.content.strip()

    except TimeoutError:
        logger.warning("summarize_transcript: request timed out channel=%s", channel)
        return "Resumen no disponible (tiempo de espera agotado)."

    except Exception:
        logger.exception("summarize_transcript: unexpected error channel=%s", channel)
        return "Resumen no disponible (error interno)."

    if not result:
        logger.warning("summarize_transcript: model returned empty response channel=%s", channel)
        return "Resumen no disponible (respuesta vacía del modelo)."

    return result


async def normalize_visit_datetime_pst(
    visit_date: str,
    visit_time: str,
) -> dict:

    _FALLBACK = {
        "visit_date": None,
        "visit_time": None,
        "visit_datetime_iso": None,
        "timezone": "America/Los_Angeles",
        "confidence": "low",
    }

    visit_date = (visit_date or "").strip()
    visit_time = (visit_time or "").strip()

    if not visit_date and not visit_time:
        logger.warning("normalize_visit_datetime_pst: both inputs are empty")
        return _FALLBACK

    reference_dt = datetime.now(PST)
    reference_date_str = reference_dt.strftime("%Y-%m-%d")
    reference_time_str = reference_dt.strftime("%H:%M")

    prompt = f"""
        Resuelve fecha y hora a valores explícitos.

        REGLAS OBLIGATORIAS:
        - Devuelve SOLO JSON válido.
        - No agregues texto adicional.
        - No expliques nada.
        - No inventes valores.
        - Ignora zona horaria.
        - Si la fecha de entrada no tiene año, asume siempre el año en curso indicado en la referencia.
        - Si la fecha y hora pueden resolverse sin ambigüedad, confidence = "high".
        - Si no hay una fecha y hora de entrada valido, confidence = "low".

        Referencia actual:
        Fecha: {reference_date_str}
        Hora: {reference_time_str}

        Entrada:
        fecha: "{visit_date}"
        hora: "{visit_time}"

        Formato EXACTO requerido:
        {{
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "confidence": "high|low"
        }}
    """

    try:
        response = await client.chat.completions.create(
            model=STD_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=25.0,
        )
    except TimeoutError:
        logger.warning("normalize_visit_datetime_pst: model request timed out")
        return _FALLBACK
    except Exception:
        logger.exception("normalize_visit_datetime_pst: model request failed")
        return _FALLBACK

    raw_text = response.choices[0].message.content.strip()
    logger.info("NORMALIZER RAW MODEL OUTPUT: %s", raw_text)

    if not raw_text:
        logger.warning("normalize_visit_datetime_pst: model returned empty response")
        return _FALLBACK

    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("normalize_visit_datetime_pst: JSON parse failed — raw=%s", raw_text)
        return _FALLBACK

    if not isinstance(data, dict):
        logger.warning("normalize_visit_datetime_pst: parsed JSON is not a dict")
        return _FALLBACK

    logger.info("NORMALIZER PARSED JSON: %s", data)
    logger.info("NORMALIZER CONFIDENCE: %s", data.get("confidence"))

    date_str = data.get("date")
    time_str = data.get("time")
    confidence = data.get("confidence", "low")

    if not isinstance(date_str, str) or not isinstance(time_str, str):
        logger.warning("normalize_visit_datetime_pst: invalid types date=%r time=%r", date_str, time_str)
        return {**_FALLBACK, "visit_date": date_str, "visit_time": time_str}

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        logger.warning("normalize_visit_datetime_pst: invalid format date=%r time=%r", date_str, time_str)
        return {**_FALLBACK, "visit_date": date_str, "visit_time": time_str}

    if confidence != "high":
        logger.info("normalize_visit_datetime_pst: low confidence date=%r time=%r", date_str, time_str)
        return {**_FALLBACK, "visit_date": date_str, "visit_time": time_str}

    try:
        dt = datetime.strptime(
            f"{date_str} {time_str}",
            "%Y-%m-%d %H:%M",
        ).replace(tzinfo=PST)
    except ValueError:
        logger.exception("normalize_visit_datetime_pst: datetime construction failed")
        return {**_FALLBACK, "visit_date": date_str, "visit_time": time_str}

    result = {
        "visit_date": dt.strftime("%Y-%m-%d"),
        "visit_time": dt.strftime("%H:%M"),
        "visit_datetime_iso": dt.isoformat(),
        "timezone": "America/Los_Angeles",
        "confidence": "high",
    }

    logger.info("NORMALIZER FINAL RESULT: %s", result)

    return result


if __name__ == "__main__":
    import asyncio

    async def test():
        result = await normalize_visit_datetime_pst(
            visit_date="jueves 12 de marzo",
            visit_time="1:00 pm",
        )
        print(result)

    asyncio.run(test())