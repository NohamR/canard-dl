"""Phenix store API — authentication and issue listing.

Handles the auth flow against phenix2.immanens.com:

  1. generate device_sign (cookie)
  2. anonymous/get-online-token → x_anonymous_token
  3. user/online-login → x_user_token + customer-hash
  4. store/default/publications → issue list
  5. store/default/get-streaming-token → access_token (for PressView5)
"""

import hashlib
import json
import random
import time

import requests

from canard_dl.logger import get_logger

logger = get_logger(__name__)

APP_ID = 343
PHENIX_URL = "https://phenix2.immanens.com"
PHENIX_API_KEY = "56c3-ce9f-eb65-2296"
HOST = "lire.lecanardenchaine.fr"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Origin": f"https://{HOST}",
    "Referer": f"https://{HOST}/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
}


def generate_device_sign() -> str:
    """Generate a 20-char base36 device identifier (matching the JS bundle)."""

    ts = time.time()
    parts = [
        int(ts * 1000).to_bytes(8, "big").hex(),
        format(random.getrandbits(64), "016x"),
    ]
    raw = hashlib.sha256("".join(parts).encode()).hexdigest()[:20]
    return raw


def get_anonymous_token(device_sign: str) -> str:
    """Get an anonymous token (step 2)."""

    url = f"{PHENIX_URL}/api/v1/app/{APP_ID}/anonymous/get-online-token"

    body = {
        "app_id": APP_ID,
        "app_secret": PHENIX_API_KEY,
        "device_auth": {
            "description": HEADERS["User-Agent"],
            "os": "browser",
            "token": {
                "crypt_mode": "none",
                "crypt_value": device_sign,
            },
        },
    }

    headers = {**HEADERS, "Content-Type": "text/plain"}

    logger.debug("POST %s", url)

    response = requests.post(
        url,
        data=json.dumps(body),
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    token = data["x_anonymous_token"]

    logger.debug("Got anonymous token (len=%d)", len(token))

    return token


def login(
    email: str,
    password: str,
    anonymous_token: str,
) -> dict:
    """Login with email/password (step 3). Returns user token + customer hash."""

    url = f"{PHENIX_URL}/api/v1/app/{APP_ID}/user/online-login"

    body = {
        "login": email,
        "password": password,
        "host": HOST,
    }

    headers = {
        **HEADERS,
        "x-anonymous-token": anonymous_token,
    }

    logger.debug("POST %s", url)

    response = requests.post(
        url,
        data=json.dumps(body),
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    customer_hash = response.headers.get("customer-hash", "")

    logger.debug("Got user token (len=%d)", len(data.get("x_user_token", "")))

    return {
        "x_user_token": data["x_user_token"],
        "customer_hash": customer_hash,
    }


def get_publications(
    user_token: str = "",
    customer_hash: str = "",
    *,
    anonymous: bool = True,
) -> list[dict]:
    """List available publications (step 4)."""

    url = f"{PHENIX_URL}/api/v1/app/{APP_ID}/store/default/publications"
    params = {"nb_by_pub": 0, "language": "fr", "ano": 1 if anonymous else 0}

    headers = {**HEADERS}

    if user_token:
        headers["x-user-token"] = user_token
    if customer_hash:
        headers["customer-hash"] = customer_hash

    logger.debug("GET %s", url)

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    publications = data.get("models", [])

    logger.debug("Found %d publication(s)", len(publications))

    return publications


def get_issues(
    publication_id: int,
    user_token: str = "",
    customer_hash: str = "",
    *,
    count: int = 12,
) -> list[dict]:
    """List issues for a publication."""

    url = f"{PHENIX_URL}/api/v1/app/{APP_ID}/store/default/publications/{publication_id}"
    params = {"nb_by_pub": count, "has_download": False, "language": "fr", "ano": 1}

    headers = {**HEADERS}

    if user_token:
        headers["x-user-token"] = user_token
    if customer_hash:
        headers["customer-hash"] = customer_hash

    logger.debug("GET %s", url)

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    issues = []
    for pub in data.get("models", []):
        for issue in pub.get("issues_data", []):
            issues.append({
                "issue_id": issue["issue_id"],
                "number": issue["number"],
                "title": issue["issue_title"],
                "pages": issue["pages"],
                "puc": issue["puc"],
                "display_date": issue["display_date"],
                "logistic_doc_id": issue["logistic_doc_id"],
            })

    logger.debug("Found %d issue(s)", len(issues))

    return issues


def get_streaming_token(
    puc: int,
    number: int,
    user_token: str,
    customer_hash: str,
) -> str:
    """Get a streaming access token for a specific issue (step 5)."""

    url = (
        f"{PHENIX_URL}/api/v1/app/{APP_ID}/store/default"
        f"/get-streaming-token/number/{puc}/{number}"
    )
    params = {"license_lock_time": 1, "language": "fr"}

    headers = {
        **HEADERS,
        "x-user-token": user_token,
        "customer-hash": customer_hash,
    }

    logger.debug("GET %s", url)

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    token = data["access_token"]

    logger.debug("Got streaming token (len=%d)", len(token))

    return token
