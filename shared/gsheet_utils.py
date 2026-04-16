from typing import Dict, List, Optional
from pathlib import Path
import logging
import os
import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger("gsheet_utils")

# =====================================================
# CONFIG
# =====================================================

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Campaign -> Spreadsheet ID
SPREADSHEET_IDS = {
    "salon_ibargo": "1fvo3qrZgvLiHUrjXgm3yxuwH3C5qgzaL43O8JJJp6OI",
    "sanatorio_quiroz": "1a-85whiTyE5NHmH70_CJKeKD0aoGzjeXqCAAyyAgprc",
}

BASE_DIR = Path(__file__).resolve().parent
LOCAL_SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"

# =====================================================
# CREDENTIAL LOADER
# =====================================================

def _load_credentials():
    """
    Loads credentials from:
    1) GOOGLE_SERVICE_ACCOUNT_JSON env var (production)
    2) local service_account.json file (local dev fallback)
    """

    json_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    # Production: load from env variable
    if json_env:
        try:
            service_account_info = json.loads(json_env)
            return Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES,
            )
        except Exception as e:
            raise RuntimeError(
                "Invalid GOOGLE_SERVICE_ACCOUNT_JSON environment variable"
            ) from e

    # Local fallback: load from file
    if LOCAL_SERVICE_ACCOUNT_FILE.exists():
        return Credentials.from_service_account_file(
            LOCAL_SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )

    raise RuntimeError(
        "No Google credentials found. "
        "Set GOOGLE_SERVICE_ACCOUNT_JSON or provide service_account.json locally."
    )

# =====================================================
# CLIENT (LAZY)
# =====================================================

_service = None

def _get_sheets_service():
    global _service
    if _service is None:
        creds = _load_credentials()
        _service = build("sheets", "v4", credentials=creds)
    return _service

# =====================================================
# HELPERS
# =====================================================

def get_spreadsheet_id_for_campaign(campaign: str) -> str:
    spreadsheet_id = SPREADSHEET_IDS.get(campaign)

    if not spreadsheet_id:
        raise ValueError(
            f"Unknown campaign '{campaign}'. "
            f"Valid campaigns: {', '.join(SPREADSHEET_IDS.keys())}"
        )

    return spreadsheet_id

# =====================================================
# PUBLIC API
# =====================================================

def append_row_to_sheet(
    *,
    campaign: str,
    sheet_name: str,
    headers: List[str],
    row: Dict,
):
    """
    Appends one row into the target sheet for the given campaign.

    Args:
        campaign: e.g. "salon_ibargo" or "sanatorio_quiroz"
        sheet_name: target tab name inside the spreadsheet
        headers: ordered list of column names to serialize
        row: dict keyed by header names
    """
    service = _get_sheets_service()
    spreadsheet_id = get_spreadsheet_id_for_campaign(campaign)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:A",
        ).execute()

        existing = result.get("values", [])
        next_row = len(existing) + 1

        values = [[row.get(h) for h in headers]]

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A{next_row}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

        logger.info(
            "sheet_row_appended campaign=%s spreadsheet_id=%s sheet=%s row=%s",
            campaign,
            spreadsheet_id,
            sheet_name,
            next_row,
        )

    except Exception as e:
        logger.exception(
            "Failed to append row campaign=%s spreadsheet_id=%s sheet=%s error=%s",
            campaign,
            spreadsheet_id,
            sheet_name,
            e,
        )
        raise

# =====================================================
# MANUAL TEST
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from datetime import datetime
    from zoneinfo import ZoneInfo

    PST = ZoneInfo("America/Los_Angeles")

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
        "From Phone Number",
        "To Phone Number",
        "Empiezo Llamada",
        "Termino Llamada",
        "Duración",
        "Transcripción",
        "Resumen",
        "Grabación",
        "ID",
    ]

    chat_row = {
        "Creado": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "Empiezo Chat": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "Termino Chat": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "Duración": 12,
        "Transcripción": "Usuario: Hola | Agente: Buenas tardes",
        "Resumen": "Prueba de chat",
        "ID": "TEST-CHAT-123",
    }

    call_row = {
        "Creado": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "From Phone Number": "+15555550111",
        "To Phone Number": "+15555550222",
        "Empiezo Llamada": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "Termino Llamada": datetime.now(tz=PST).strftime("%Y-%m-%d %H:%M:%S"),
        "Duración": 34,
        "Transcripción": "Usuario: Hola | Agente: ¿En qué le ayudo?",
        "Resumen": "Prueba de llamada",
        "Grabación": "https://example.com/recording/test-call",
        "ID": "TEST-CALL-123",
    }

    logger.info("Appending test chat row to Salon Ibargo...")
    append_row_to_sheet(
        campaign="salon_ibargo",
        sheet_name="Chats",
        headers=CHAT_HEADERS,
        row=chat_row,
    )

    logger.info("Appending test call row to Sanatorio Quiroz...")
    append_row_to_sheet(
        campaign="sanatorio_quiroz",
        sheet_name="Llamadas",
        headers=CALL_HEADERS,
        row=call_row,
    )

    logger.info("Done.")