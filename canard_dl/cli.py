"""Command-line interface: download a single article."""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from canard_dl.article import (
    clean_article,
    extract_text,
    find_article,
    sanitize_html,
    unlock_paywall,
)
from canard_dl.logger import get_logger, setup_logging
from canard_dl.spoofer import fetch

logger = get_logger(__name__)


def make_filename(url: str) -> str:
    """Generate a filename from the article URL."""

    path = urlparse(url).path.rstrip("/")

    slug = path.split("/")[-1]

    if not slug:
        slug = "article"

    slug = re.sub(
        r"[^a-zA-Z0-9À-ÿ_-]+",
        "_",
        slug,
    )

    return slug[:150]


def extract(url: str, output_dir: Path) -> None:
    logger.info("Downloading: %s", url)

    html = fetch(url)

    logger.info("Downloaded %s bytes", f"{len(html):,}")

    soup = BeautifulSoup(html, "html.parser")

    # Remove CSS paywall.
    logger.debug("Unlocking CSS paywall")
    unlock_paywall(soup)

    # Remove page junk.
    logger.debug("Cleaning article")
    clean_article(soup)

    heading, editorial = find_article(soup)

    if not heading and not editorial:
        raise RuntimeError(
            "Could not find the article content. "
            "The site's HTML structure may have changed."
        )

    # Extract title.
    title = None

    for container in (heading, editorial):
        if container is None:
            continue

        title_tag = container.find(["h1", "h2"])

        if title_tag:
            title = title_tag.get_text(" ", strip=True)
            break

    if not title:
        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else "Le Canard Enchaîné"
        )

    logger.debug("Found title: %s", title)

    text = extract_text(heading, editorial)
    article_html = sanitize_html(heading, editorial)

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = make_filename(url)

    html_path = output_dir / f"{filename}.html"
    text_path = output_dir / f"{filename}.txt"

    html_path.write_text(article_html, encoding="utf-8")
    text_path.write_text(f"{title}\n\n{text}", encoding="utf-8")

    logger.info("Title : %s", title)
    logger.info("HTML  : %s", html_path)
    logger.info("Text  : %s", text_path)
    logger.info("Text size: %s characters", f"{len(text):,}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract an article from Le Canard Enchaîné "
            "from a single URL."
        )
    )

    parser.add_argument(
        "url",
        help="URL of the article",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory (default: output)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only log warnings and errors",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    if not args.url.startswith(("http://", "https://")):
        logger.error("URL must start with http:// or https://")
        sys.exit(1)

    try:
        extract(args.url, Path(args.output))
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()