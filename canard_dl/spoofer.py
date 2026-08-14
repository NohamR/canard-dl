"""HTTP fetching with a Googlebot spoofer.

The Canard serves the full article content to Google robots (for
indexing). The premium content is hidden with a CSS paywall only, so
no login is required. We impersonate Googlebot to get the complete
article.

Inspired by the Calibre recipe:
https://github.com/debian-calibre/calibre/blob/37ec650f9dd717c235c96344eea74970959781b2/recipes/le_canard_enchaine.recipe#L24
"""

import requests

from canard_dl.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.lecanardenchaine.fr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; "
        "+http://www.google.com/bot.html)"
    ),
    "Referer": "https://www.google.fr/",
    "X-Forwarded-For": "66.249.66.1",  # Official Googlebot IP
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
}


def fetch(url: str, *, timeout: int = 30) -> str:
    """Download the HTML of the given URL."""

    logger.debug("GET %s (timeout=%ss)", url, timeout)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    # requests normally detects this correctly, but the site may not
    # always provide the expected charset.
    if not response.encoding:
        response.encoding = response.apparent_encoding

    logger.debug(
        "Status %s, %s bytes, encoding=%s",
        response.status_code,
        f"{len(response.content):,}",
        response.encoding,
    )

    return response.text
