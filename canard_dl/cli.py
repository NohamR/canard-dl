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
from canard_dl.spoofer import fetch


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
    print(f"[+] Downloading: {url}")

    html = fetch(url)

    print(f"[+] Downloaded {len(html):,} bytes")

    soup = BeautifulSoup(html, "html.parser")

    # Remove CSS paywall.
    unlock_paywall(soup)

    # Remove page junk.
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

    text = extract_text(heading, editorial)
    article_html = sanitize_html(heading, editorial)

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = make_filename(url)

    html_path = output_dir / f"{filename}.html"
    text_path = output_dir / f"{filename}.txt"

    html_path.write_text(article_html, encoding="utf-8")
    text_path.write_text(f"{title}\n\n{text}", encoding="utf-8")

    print()
    print(f"[+] Title : {title}")
    print(f"[+] HTML  : {html_path}")
    print(f"[+] Text  : {text_path}")
    print(f"[+] Text size: {len(text):,} characters")


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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        print(
            "Error: URL must start with http:// or https://",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        extract(args.url, Path(args.output))
    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()