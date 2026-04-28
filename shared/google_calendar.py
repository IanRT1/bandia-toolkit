"""
shared/google_calendar.py
--------------------------------
Thin wrapper around Google Calendar API.

Currently supports:
- is_slot_available(): check if a proposed time has any conflicting events

Will later support:
- create_event(): book the appointment after the call ends

Auth flow: uses get_access_token() from google_oauth.py to mint a fresh
access token from the campaign's stored refresh token on every call.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from shared.google_oauth import get_access_token


logger = logging.getLogger("google_calendar")


# =====================================================
# CONFIG
# =====================================================

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
PST = ZoneInfo("America/Los_Angeles")

# Default calendar ID. "primary" means whatever the authenticated user
# considers their main calendar. Override per-campaign if needed.
DEFAULT_CALENDAR_ID = "primary"


# =====================================================
# AVAILABILITY CHECK
# =====================================================

async def is_slot_available(
    campaign: str,
    visit_date: str,           # "YYYY-MM-DD"
    visit_time: str,           # "HH:MM" (24h)
    duration_minutes: int = 60,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> dict:
    """
    Checks if the proposed slot has any conflicting events on the
    campaign's connected Google Calendar.

    Returns:
        {
            "available": bool,
            "conflicts": [ {summary, start, end}, ... ],
            "checked_range": {"start": iso, "end": iso},
        }

    Raises:
        RuntimeError if auth or API call fails.
    """

    # Build the proposed time range in PST, then send to Google as ISO with offset.
    try:
        start_dt = datetime.strptime(
            f"{visit_date} {visit_time}",
            "%Y-%m-%d %H:%M",
        ).replace(tzinfo=PST)
    except ValueError as e:
        raise RuntimeError(f"Invalid date/time format: {e}")

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

    logger.info(
        "is_slot_available campaign=%s range=%s -> %s",
        campaign,
        time_min,
        time_max,
    )

    # Get a fresh access token
    access_token = await get_access_token(campaign)

    # Query events that overlap [time_min, time_max)
    url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events"
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",         # expand recurring events
        "orderBy": "startTime",
        "maxResults": 50,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params, headers=headers)

    if response.status_code != 200:
        logger.error(
            "Calendar API error campaign=%s status=%s body=%s",
            campaign,
            response.status_code,
            response.text,
        )
        raise RuntimeError(
            f"Calendar API returned {response.status_code}: {response.text}"
        )

    data = response.json()
    events = data.get("items", [])

    # Filter out events that are marked "transparent" (i.e. "available" in
    # Google Calendar terminology — they don't actually block your time).
    conflicts = []
    for ev in events:
        if ev.get("transparency") == "transparent":
            continue

        # Skip cancelled events (shouldn't appear with singleEvents=true, but safety)
        if ev.get("status") == "cancelled":
            continue

        conflicts.append({
            "summary": ev.get("summary", "(sin título)"),
            "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date"),
            "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date"),
        })

    available = len(conflicts) == 0

    logger.info(
        "is_slot_available campaign=%s available=%s conflicts=%d",
        campaign,
        available,
        len(conflicts),
    )

    return {
        "available": available,
        "conflicts": conflicts,
        "checked_range": {
            "start": time_min,
            "end": time_max,
        },
    }