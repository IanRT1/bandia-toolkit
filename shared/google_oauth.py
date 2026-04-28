"""
shared/google_oauth.py
--------------------------------
One-time OAuth setup flow for granting Calendar access per campaign.

Each client has its own Google Cloud project, so OAuth credentials
(client_id, client_secret) are also per-campaign. Env vars:

    <CAMPAIGN>_GOOGLE_OAUTH_CLIENT_ID
    <CAMPAIGN>_GOOGLE_OAUTH_CLIENT_SECRET
    <CAMPAIGN>_GOOGLE_REFRESH_TOKEN     (set after running OAuth flow)

Plus one global:
    OAUTH_REDIRECT_BASE                 (public URL of this service)

Flow:
1. Operator hits /oauth/google/connect?campaign=vg_consultoria
2. Backend redirects to Google's consent screen
3. Client (or test user) authorizes
4. Google redirects back to /oauth/google/callback with an auth code
5. Backend exchanges the code for a refresh token
6. Refresh token is shown in browser response
7. Operator copies it into Render env vars as <CAMPAIGN>_GOOGLE_REFRESH_TOKEN
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse


logger = logging.getLogger("google_oauth")


# =====================================================
# CONFIG
# =====================================================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]

OAUTH_REDIRECT_BASE = os.environ.get(
    "OAUTH_REDIRECT_BASE",
    "https://bandia-toolkit-qwt3.onrender.com",
)

REDIRECT_URI = f"{OAUTH_REDIRECT_BASE}/oauth/google/callback"


# =====================================================
# PER-CAMPAIGN CREDENTIAL LOOKUP
# =====================================================

def _get_client_credentials(campaign: str) -> tuple[str, str]:
    """
    Each client lives in its own Google Cloud project, so each campaign
    has its own OAuth client_id / client_secret.
    """
    prefix = campaign.upper()
    client_id = os.environ.get(f"{prefix}_GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get(f"{prefix}_GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            f"Missing OAuth credentials for campaign={campaign}. "
            f"Set {prefix}_GOOGLE_OAUTH_CLIENT_ID and "
            f"{prefix}_GOOGLE_OAUTH_CLIENT_SECRET in env."
        )

    return client_id, client_secret


# =====================================================
# STEP 1: BUILD CONSENT URL AND REDIRECT
# =====================================================

async def start_oauth_flow(campaign: str):
    if not campaign:
        raise HTTPException(
            status_code=400,
            detail="campaign query param is required",
        )

    try:
        client_id, _ = _get_client_credentials(campaign)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": campaign,
    }

    consent_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    logger.info("Starting OAuth flow campaign=%s", campaign)

    return RedirectResponse(url=consent_url)


# =====================================================
# STEP 2: HANDLE CALLBACK FROM GOOGLE
# =====================================================

async def handle_oauth_callback(request: Request):
    params = request.query_params

    error = params.get("error")
    if error:
        logger.warning("OAuth callback error: %s", error)
        return HTMLResponse(
            content=f"<h2>OAuth error</h2><p>{error}</p>",
            status_code=400,
        )

    code = params.get("code")
    campaign = params.get("state")

    if not code or not campaign:
        raise HTTPException(
            status_code=400,
            detail="Missing code or state in callback",
        )

    try:
        client_id, client_secret = _get_client_credentials(campaign)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    token_payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=token_payload)

    if response.status_code != 200:
        logger.error(
            "Token exchange failed campaign=%s status=%s body=%s",
            campaign,
            response.status_code,
            response.text,
        )
        return HTMLResponse(
            content=(
                f"<h2>Token exchange failed</h2>"
                f"<p>Status: {response.status_code}</p>"
                f"<pre>{response.text}</pre>"
            ),
            status_code=500,
        )

    tokens = response.json()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        logger.error(
            "No refresh_token in response. User may have already granted "
            "access without prompt=consent. Tokens: %s",
            tokens,
        )
        return HTMLResponse(
            content=(
                "<h2>No refresh token returned</h2>"
                "<p>This usually happens when the user already authorized this app before. "
                "Go to <a href='https://myaccount.google.com/permissions'>myaccount.google.com/permissions</a>, "
                "revoke access for this app, then try again.</p>"
            ),
            status_code=400,
        )

    env_var_name = f"{campaign.upper()}_GOOGLE_REFRESH_TOKEN"
    logger.info(
        "OAuth success campaign=%s. Set Render env var:\n%s=%s",
        campaign,
        env_var_name,
        refresh_token,
    )

    html = f"""
    <html>
      <head><title>OAuth Success</title></head>
      <body style="font-family: monospace; padding: 2rem; max-width: 800px;">
        <h2>✅ Google Calendar connected for: {campaign}</h2>
        <p><strong>Step 1:</strong> Copy this refresh token:</p>
        <textarea readonly style="width:100%; height:6rem; padding:0.5rem;">{refresh_token}</textarea>

        <p><strong>Step 2:</strong> In Render dashboard, add an environment variable:</p>
        <pre style="background:#222; color:#0f0; padding:1rem;">{env_var_name}={refresh_token}</pre>

        <p><strong>Step 3:</strong> Redeploy. Done.</p>

        <hr>
        <details>
          <summary>Debug info</summary>
          <pre>{tokens}</pre>
        </details>
      </body>
    </html>
    """

    return HTMLResponse(content=html)


# =====================================================
# RUNTIME: GET A FRESH ACCESS TOKEN
# =====================================================

async def get_access_token(campaign: str) -> str:
    """
    Used at runtime by the calendar wrapper.
    Reads the stored refresh token from env vars and exchanges it
    for a short-lived access token.
    """

    prefix = campaign.upper()
    refresh_token = os.environ.get(f"{prefix}_GOOGLE_REFRESH_TOKEN")

    if not refresh_token:
        raise RuntimeError(
            f"Missing {prefix}_GOOGLE_REFRESH_TOKEN. Run the OAuth flow first: "
            f"GET /oauth/google/connect?campaign={campaign}"
        )

    client_id, client_secret = _get_client_credentials(campaign)

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)

    if response.status_code != 200:
        logger.error(
            "Refresh failed campaign=%s status=%s body=%s",
            campaign,
            response.status_code,
            response.text,
        )
        raise RuntimeError(
            f"Failed to refresh access token for {campaign}: {response.text}"
        )

    data = response.json()
    access_token = data.get("access_token")

    if not access_token:
        raise RuntimeError(f"No access_token in refresh response: {data}")

    return access_token