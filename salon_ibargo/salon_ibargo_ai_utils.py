# ai_utils.py

from typing import List
import os
import logging
import asyncio

from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI

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

client = OpenAI(api_key=OPENAI_API_KEY)

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
    """
    Expects:
    [
        {"role": "user" | "assistant", "content": "text"},
        ...
    ]
    """

    return " | ".join(
        f"{item['role'].upper()}: {item['content'].replace('\n', ' ').strip()}"
        for item in transcript
        if item.get("content")
    )

def extract_text(response) -> str:
    for item in response.output:
        # Only items that actually contain content
        if hasattr(item, "content") and item.content:
            for content in item.content:
                if getattr(content, "type", None) == "output_text":
                    return content.text.strip()
    return ""



# -------------------------------------------------
# Public API
# -------------------------------------------------

async def summarize_transcript(transcript: List[TranscriptItem]) -> str:
    """
    Summarize a call transcript into ONE short paragraph.
    """

    transcript_text = transcript_to_single_line(transcript)

    prompt = (
        "Resume la siguiente llamada telefónica en UN SOLO PÁRRAFO breve. "
        "No uses listas ni encabezados. "
        "Describe la intención del cliente y cómo terminó la llamada.\n\n"
        f"{transcript_text}"
    )

    logger.info(f"summarize_transcript: calling {SUM_MODEL}")

    response = client.responses.create(
        model=SUM_MODEL,
        input=prompt,
    )

    return extract_text(response)


async def normalize_visit_datetime_pst(
    visit_date: str,
    visit_time: str,
) -> dict:

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
        - Si la fecha y hora pueden resolverse sin ambigüedad, confidence = "high".
        - Si existe cualquier ambigüedad real, confidence = "low".

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
        response = await client.responses.create(
            model=STD_MODEL,
            input=prompt,
        )

        raw_text = extract_text(response)
        logger.info("NORMALIZER RAW MODEL OUTPUT: %s", raw_text)

        data = json.loads(raw_text)

    except Exception as e:
        logger.exception("Normalizer model or JSON parsing failed")
        return {
            "visit_date": None,
            "visit_time": None,
            "visit_datetime_iso": None,
            "timezone": "America/Los_Angeles",
            "confidence": "low",
        }

    logger.info("NORMALIZER PARSED JSON: %s", data)
    logger.info("NORMALIZER CONFIDENCE: %s", data.get("confidence"))

    # -------------------------------------------------
    # HARD TYPE VALIDATION
    # -------------------------------------------------

    date_str = data.get("date")
    time_str = data.get("time")
    confidence = data.get("confidence", "low")

    if not isinstance(date_str, str) or not isinstance(time_str, str):
        logger.warning("Normalizer returned invalid types")
        return {
            "visit_date": date_str,
            "visit_time": time_str,
            "visit_datetime_iso": None,
            "timezone": "America/Los_Angeles",
            "confidence": "low",
        }

    # -------------------------------------------------
    # FORMAT VALIDATION
    # -------------------------------------------------

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        datetime.strptime(time_str, "%H:%M")
    except Exception:
        logger.warning("Normalizer returned invalid date/time format")
        return {
            "visit_date": date_str,
            "visit_time": time_str,
            "visit_datetime_iso": None,
            "timezone": "America/Los_Angeles",
            "confidence": "low",
        }

    # -------------------------------------------------
    # CONFIDENCE CHECK
    # -------------------------------------------------

    if confidence != "high":
        logger.info("Visit date/time not high confidence")
        return {
            "visit_date": date_str,
            "visit_time": time_str,
            "visit_datetime_iso": None,
            "timezone": "America/Los_Angeles",
            "confidence": "low",
        }

    # -------------------------------------------------
    # SAFE DATETIME CONSTRUCTION
    # -------------------------------------------------

    dt = datetime.strptime(
        f"{date_str} {time_str}",
        "%Y-%m-%d %H:%M",
    ).replace(tzinfo=PST)

    result = {
        "visit_date": dt.strftime("%Y-%m-%d"),
        "visit_time": dt.strftime("%H:%M"),
        "visit_datetime_iso": dt.isoformat(),
        "timezone": "America/Los_Angeles",
        "confidence": "high",
    }

    logger.info("NORMALIZER FINAL RESULT: %s", result)

    return result



# -------------------------------------------------
# Self-test
# -------------------------------------------------

if __name__ == "__main__":

    async def _test():
        print("=== ai_utils self-test ===\n")

        normalized = await normalize_visit_datetime_pst(
            visit_date="2026-01-20",
            visit_time="7 pm",
            current_datetime="domingo, 19/01/2026 05:45PM PST",
        )

        print("Normalized Datetime:")
        print(normalized)
        print()

        transcript = [
            TranscriptItem(role="user", content="Hola, quiero saber si hay fechas disponibles."),
            TranscriptItem(role="assistant", content="Claro, ¿qué fecha tienes en mente?"),
            TranscriptItem(role="user", content="El 20 de enero por la tarde."),
            TranscriptItem(role="assistant", content="Perfecto, esa fecha está disponible."),
        ]

        summary = await summarize_transcript(transcript)

        print("Transcript summary:")
        print(summary)
        print("\n=== ai_utils self-test completed ===")

    asyncio.run(_test())
