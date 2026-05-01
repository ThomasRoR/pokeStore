"""Business logic and services."""
import os
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request
import json

from fastapi import HTTPException

POKEWALLET_BASE_URL = "https://api.pokewallet.io"


def normalize_card_code(value: str) -> str:
    """Normalize card code."""
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def normalize_card_number(value: str) -> str:
    """Normalize card number."""
    head = (value or "").strip().split("/", 1)[0]
    normalized = normalize_card_code(head)
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


def get_pokewallet_key() -> str:
    """Get PokéWallet API key from env."""
    api_key = os.getenv("POKEWALLET_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="POKEWALLET_API_KEY nao configurada no backend.",
        )
    return api_key


def pokewallet_auth_headers_variants(api_key: str) -> list[dict[str, str]]:
    """Return possible auth header variants for PokéWallet."""
    return [
        {"X-API-Key": api_key},
        {"Authorization": f"Bearer {api_key}"},
    ]


def pokewallet_client_headers() -> dict[str, str]:
    """Return client headers for PokéWallet API calls."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }


def fetch_pokewallet_sets(language: str) -> list[dict]:
    """Fetch sets from PokéWallet API."""
    api_key = get_pokewallet_key()
    lang_param = "jap" if language == "ja" else language

    for auth_header in pokewallet_auth_headers_variants(api_key):
        headers = {**pokewallet_client_headers(), **auth_header}
        req = url_request.Request(
            f"{POKEWALLET_BASE_URL}/sets?language={lang_param}",
            headers=headers,
        )

        try:
            with url_request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
                if isinstance(data.get("sets"), list):
                    return data["sets"]
        except (url_error.URLError, url_error.HTTPError, TimeoutError):
            pass

    raise HTTPException(
        status_code=503, detail="Falha ao buscar sets do PokéWallet."
    )


def fetch_pokewallet_card(colecao_id: str, codigo_carta: str, nome_carta: str = "") -> str | None:
    """Fetch card image from PokéWallet API, returns card_id or None."""
    api_key = get_pokewallet_key()
    params = url_parse.urlencode({
        "colecao_id": colecao_id,
        "codigo_carta": codigo_carta,
        "nome_carta": nome_carta,
    })

    for auth_header in pokewallet_auth_headers_variants(api_key):
        headers = {**pokewallet_client_headers(), **auth_header}
        req = url_request.Request(
            f"{POKEWALLET_BASE_URL}/cards/search?{params}",
            headers=headers,
        )

        try:
            with url_request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("found") and data.get("card_id"):
                    return data["card_id"]
        except (url_error.URLError, url_error.HTTPError, TimeoutError):
            pass

    return None


def pokewallet_image_url(card_id: str, size: str = "low") -> str:
    """Get proxied image URL for PokéWallet card."""
    return f"/integracoes/pokewallet/images/{card_id}?size={size}"
