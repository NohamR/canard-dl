"""Scrape the section index pages for recent articles."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from canard_dl.logger import get_logger
from canard_dl.spoofer import BASE_URL, fetch

logger = get_logger(__name__)

PARIS = ZoneInfo("Europe/Paris")


def normalize(name: str) -> str:
    """Lowercase and strip accents for comparison."""

    return "".join(
        c for c in unicodedata.normalize("NFD", name.lower())
        if not unicodedata.combining(c)
    )

SECTIONS = {
    "Politique": "/politique/",
    "Économie": "/economie/",
    "International": "/international/",
    "Défense": "/defense/",
    "Société": "/societe/",
    "Police-Justice": "/police-justice/",
    "Santé": "/sante/",
    "Éducation": "/education/",
    "Environnement": "/environnement/",
    "Technologie-Sciences": "/technologie-sciences/",
    "Culture-Idées": "/culture-idees/",
    "Médias": "/medias/",
    "Sport": "/sport/",
    "Social": "/social/",
    "Brèves": "/breves/",
}


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    date: datetime
    section: str


def fetch_section_articles(section: str, path: str) -> list[Article]:
    """Parse a single section page and return its articles."""

    logger.debug("Fetching section %s (%s)", section, path)

    soup = BeautifulSoup(fetch(BASE_URL + path), "html.parser")

    articles = []

    for item in soup.find_all("article", class_="article-item"):
        link = item.find("a", href=True)
        date_div = item.find("div", class_="article-item__date")

        if link is None or date_div is None:
            continue

        time_element = date_div.find("time")

        if time_element is None or not time_element.get("datetime"):
            continue

        url = link["href"]

        if not url.startswith("http"):
            url = BASE_URL + url

        articles.append(
            Article(
                title=link.get_text(" ", strip=True),
                url=url,
                date=datetime.fromisoformat(time_element["datetime"]),
                section=section,
            )
        )

    logger.debug("%s articles in %s", len(articles), section)

    return articles


def list_recent(*, section: str | None = None, days: int = 7) -> list[Article]:
    """Collect recent articles across the wanted sections."""

    cutoff = datetime.now(PARIS) - timedelta(days=days)

    sections = {
        name: path
        for name, path in SECTIONS.items()
        if section is None or normalize(name) == normalize(section)
    }

    if section and not sections:
        logger.warning(
            "Unknown section %r. Known sections: %s",
            section,
            ", ".join(SECTIONS),
        )

    found: list[Article] = []

    for name, path in sections.items():
        try:
            articles = fetch_section_articles(name, path)
        except Exception as e:
            logger.warning("Failed to fetch section %s: %s", name, e)
            continue

        for article in articles:
            if article.date.date() <= cutoff.date():
                continue

            found.append(article)

    found.sort(key=lambda article: article.date, reverse=True)

    return found