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
# OpenAI client
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

async def summarize_transcript(transcript: List[TranscriptItem]) -> str:

    medium = "llamada telefónica"
    ghost_label = "Llamada Fantasma 👻"

    transcript_dicts = [
        item if isinstance(item, dict) else vars(item)
        for item in transcript
    ]

    user_turns = [item for item in transcript_dicts if item.get("role") == "user"]
    user_content = " ".join(
        item.get("content", "") or "" for item in user_turns
    ).strip()

    if not user_content or len(user_content) < 10:
        logger.info("summarize_transcript: ghost detected (no user input)")
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

    logger.info("summarize_transcript: calling %s", SUM_MODEL)

    try:
        response = await client.responses.create(
            model=SUM_MODEL,
            input=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )

        result = response.output_text.strip()

    except TimeoutError:
        logger.warning("summarize_transcript: request timed out")
        return "Resumen no disponible (tiempo de espera agotado)."

    except Exception:
        logger.exception("summarize_transcript: unexpected error")
        return "Resumen no disponible (error interno)."

    if not result:
        logger.warning("summarize_transcript: model returned empty response")
        return "Resumen no disponible (respuesta vacía del modelo)."

    return result


