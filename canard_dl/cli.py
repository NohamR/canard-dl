"""Command-line interface: download a single article or pick one
from a list."""

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
from canard_dl.index import list_recent
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
            "from a single URL or pick one from the latest list."
        )
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="URL of the article (optional when using --list)",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory (default: output)",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List recent articles and pick one to download",
    )

    parser.add_argument(
        "--section",
        help="Restrict the list to a section (default: all sections)",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Only list articles from the last N days (default: 7)",
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


def pick_article(*, section: str | None, days: int) -> str | None:
    """Show the recent articles and return the chosen URL."""

    articles = list_recent(section=section, days=days)

    if not articles:
        logger.error("No recent articles found")
        return None

    print()
    print("Recent articles:")
    print()

    for i, article in enumerate(articles, 1):
        print(
            f"{i:3}. [{article.section}] "
            f"{article.date:%d/%m/%Y} — {article.title}"
        )
        print(f"       {article.url}")

    print()

    while True:
        try:
            choice = input(
                f"Pick an article to download "
                f"(1-{len(articles)}, Enter to quit): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not choice:
            return None

        if choice.isdigit() and 1 <= int(choice) <= len(articles):
            return articles[int(choice) - 1].url

        logger.warning("Invalid choice, try again")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        if args.list:
            url = pick_article(section=args.section, days=args.days)

            if url:
                extract(url, Path(args.output))
        else:
            if not args.url or not args.url.startswith(("http://", "https://")):
                logger.error("URL must start with http:// or https://")
                sys.exit(1)

            extract(args.url, Path(args.output))

    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()