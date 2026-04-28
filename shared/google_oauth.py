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

After consent, the refresh token is logged to server logs (Render).
The client only sees a clean confirmation page.
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
# HELPERS
# =====================================================

def _get_client_credentials(campaign: str) -> tuple[str, str]:
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


def _format_campaign_name(campaign: str) -> str:
    overrides = {
        "vg_consultoria": "VG Consultoría",
        "salon_ibargo": "Salón Ibargo",
        "sanatorio_quiroz": "Sanatorio Quiroz",
    }
    return overrides.get(campaign, campaign.replace("_", " ").title())


# =====================================================
# STEP 1: BUILD CONSENT URL AND REDIRECT
# =====================================================

async def start_oauth_flow(campaign: str):
    if not campaign:
        raise HTTPException(status_code=400, detail="campaign query param is required")

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

def _render_error_page(title: str, message: str, status: int = 400) -> HTMLResponse:
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f7f7f8;
            color: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 1rem;
          }}
          .card {{
            background: white;
            border-radius: 12px;
            padding: 2.5rem 2rem;
            max-width: 440px;
            width: 100%;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            text-align: center;
          }}
          h1 {{
            font-size: 1.4rem;
            margin: 0 0 0.75rem;
            color: #c0392b;
          }}
          p {{
            color: #555;
            line-height: 1.5;
            margin: 0;
          }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>⚠️ {title}</h1>
          <p>{message}</p>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=status)


def _render_success_page(campaign_label: str) -> HTMLResponse:
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <title>Conexión exitosa</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #f6f9fc 0%, #e9f2fb 100%);
            color: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 1rem;
          }}
          .card {{
            background: white;
            border-radius: 16px;
            padding: 3rem 2.5rem;
            max-width: 460px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
            text-align: center;
          }}
          .check {{
            width: 72px;
            height: 72px;
            border-radius: 50%;
            background: #e8f5e9;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 1.5rem;
            font-size: 2.5rem;
          }}
          h1 {{
            font-size: 1.5rem;
            margin: 0 0 0.5rem;
            color: #1a1a1a;
            font-weight: 600;
          }}
          .subtitle {{
            color: #2e7d32;
            font-weight: 500;
            margin: 0 0 1.5rem;
          }}
          p {{
            color: #666;
            line-height: 1.6;
            margin: 0 0 1rem;
          }}
          .footer {{
            margin-top: 2rem;
            font-size: 0.85rem;
            color: #999;
          }}
        </style>
      </head>
      <body>
        <div class="card">
          <div class="check">✅</div>
          <h1>Calendario conectado</h1>
          <p class="subtitle">{campaign_label}</p>
          <p>Tu Google Calendar quedó vinculado correctamente. Ya puedes cerrar esta ventana.</p>
          <div class="footer">No se requieren más acciones de tu parte.</div>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


async def handle_oauth_callback(request: Request):
    params = request.query_params

    error = params.get("error")
    if error:
        logger.warning("OAuth callback error: %s", error)
        return _render_error_page(
            "Conexión cancelada",
            "No se completó la autorización con Google. Si fue un error, "
            "puedes intentarlo de nuevo desde el enlace original.",
        )

    code = params.get("code")
    campaign = params.get("state")

    if not code or not campaign:
        return _render_error_page(
            "Solicitud inválida",
            "Faltan parámetros en la respuesta de Google. Intenta de nuevo.",
        )

    try:
        client_id, client_secret = _get_client_credentials(campaign)
    except RuntimeError as e:
        logger.exception("Missing credentials for callback")
        return _render_error_page("Error de configuración", str(e), status=500)

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
        return _render_error_page(
            "No se pudo completar la conexión",
            "Hubo un problema al confirmar tu autorización con Google. "
            "Por favor intenta de nuevo más tarde.",
            status=500,
        )

    tokens = response.json()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        logger.error(
            "No refresh_token in response. User may have already granted "
            "access without prompt=consent. Tokens: %s",
            tokens,
        )
        return _render_error_page(
            "Reconexión necesaria",
            "Parece que ya habías autorizado esta aplicación antes. "
            "Por favor revoca el acceso anterior en tu cuenta de Google "
            "y vuelve a intentarlo.",
        )

    # Log the refresh token server-side. Operator grabs it from Render logs.
    env_var_name = f"{campaign.upper()}_GOOGLE_REFRESH_TOKEN"
    logger.info(
        "OAuth success campaign=%s. Set Render env var:\n%s=%s",
        campaign,
        env_var_name,
        refresh_token,
    )

    return _render_success_page(_format_campaign_name(campaign))


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