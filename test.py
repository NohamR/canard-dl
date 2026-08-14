#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone Le Canard Enchaîné article extractor (PoC).

Usage:
    python test.py "https://www.lecanardenchaine.fr/societe/..."

Output:
    - <slug>.html
    - <slug>.txt

The article content is extracted from the HTML returned by the website.
The premium content is already present in the HTML (CSS paywall) —
no login is required.
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.lecanardenchaine.fr"

HEADERS = {
    # Spoof Googlebot so the Canard serves the full article content
    # (it does so for indexing). The premium content is hidden with a
    # CSS paywall only, no login required.
    # Inspired by the Calibre recipe:
    # https://github.com/debian-calibre/calibre/blob/37ec650f9dd717c235c96344eea74970959781b2/recipes/le_canard_enchaine.recipe#L24
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


def fetch_article(url: str) -> str:
    """Download the article HTML."""

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    # requests normally detects this correctly, but the site may not
    # always provide the expected charset.
    if not response.encoding:
        response.encoding = response.apparent_encoding

    return response.text


def unlock_paywall(soup: BeautifulSoup):
    """
    Remove the CSS classes/IDs used to hide the article content.

    The content itself is already present in the HTML.
    """

    # <div id="paywall">
    for element in soup.find_all("div", id="paywall"):
        element.attrs.pop("id", None)
        element.attrs.pop("class", None)

    # <div class="paywall">
    for element in soup.find_all(
        "div",
        class_=lambda classes: classes and "paywall" in classes,
    ):
        classes = (element.attrs or {}).get("class", [])
        classes = [
            cls for cls in classes
            if cls != "paywall"
        ]

        if classes:
            element["class"] = classes
        else:
            element.attrs.pop("class", None)

    # <div class="non-paywall">
    for element in soup.find_all(
        "div",
        class_=lambda classes: classes and "non-paywall" in classes,
    ):
        classes = (element.attrs or {}).get("class", [])
        classes = [
            cls for cls in classes
            if cls != "non-paywall"
        ]

        if classes:
            element["class"] = classes
        else:
            element.attrs.pop("class", None)


def clean_article(soup: BeautifulSoup):
    """Remove everything that isn't useful article content."""

    # Remove scripts, styles and page navigation.
    for element in soup.find_all(
        ["script", "style", "nav", "header", "footer", "button", "form"]
    ):
        element.decompose()

    # Remove known non-article elements.
    unwanted_classes = {
        "share-mobile",
        "share-sticky",
        "article__author",
        "article__tags",
        "list-breadcrumb",
        "modal",
    }

    for element in soup.find_all(class_=True):
        classes = set((element.attrs or {}).get("class", []))

        if classes & unwanted_classes:
            element.decompose()

    return soup


def find_article(soup: BeautifulSoup):
    """
    Find the article content using several possible structures.
    """

    heading = soup.find("div", class_="article__heading")

    editorial = soup.find("div", class_="editorial")

    # Current/fallback structure
    if editorial is None:
        article = soup.find("article")

        if article is not None:
            return heading, article

    # Another possible structure
    if heading is None:
        h1 = soup.find("h1")

        if h1 is not None:
            heading = h1.parent

    return heading, editorial


def extract_text(*elements) -> str:
    chunks = []

    for element in elements:
        if element is None:
            continue

        text = element.get_text(
            "\n",
            strip=True,
        )

        if text:
            chunks.append(text)

    text = "\n\n".join(chunks)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def sanitize_html(*elements) -> str:
    """
    Produce a minimal standalone HTML document containing
    only the article.
    """

    body = []

    for element in elements:
        if not element:
            continue

        # Remove attributes that aren't useful anymore.
        for tag in element.find_all(True):
            for attr in list(tag.attrs):
                if attr not in {
                    "href",
                    "src",
                    "class",
                }:
                    del tag.attrs[attr]

        body.append(str(element))

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Le Canard Enchaîné</title>

<style>
body {{
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    font-family: Georgia, serif;
    line-height: 1.6;
}}

h1, h2 {{
    font-family: Arial, sans-serif;
}}

.editorial__chapo {{
    font-style: italic;
    margin-bottom: 1em;
}}

img {{
    max-width: 100%;
    height: auto;
}}

a {{
    color: black;
    text-decoration: none;
}}

.zoom {{
    border-left: 3px solid #ccc;
    padding-left: 1em;
    margin: 1em 0;
}}
</style>
</head>

<body>
{"".join(body)}
</body>
</html>
"""


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


def extract(url: str, output_dir: Path):
    print(f"[+] Downloading: {url}")

    html = fetch_article(url)

    with open("debug.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("[+] Saved debug.html")

    print(f"[+] Downloaded {len(html):,} bytes")

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

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

    if heading:
        title_tag = heading.find(["h1", "h2"])

        if title_tag:
            title = title_tag.get_text(
                " ",
                strip=True,
            )

    if not title and editorial:
        title_tag = editorial.find(["h1", "h2"])

        if title_tag:
            title = title_tag.get_text(
                " ",
                strip=True,
            )

    if not title:
        title = soup.title.get_text(
            " ",
            strip=True,
        ) if soup.title else "Le Canard Enchaîné"

    text = extract_text(
        heading,
        editorial,
    )

    article_html = sanitize_html(
        heading,
        editorial,
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = make_filename(url)

    html_path = output_dir / f"{filename}.html"
    text_path = output_dir / f"{filename}.txt"

    html_path.write_text(
        article_html,
        encoding="utf-8",
    )

    text_path.write_text(
        f"{title}\n\n{text}",
        encoding="utf-8",
    )

    print()
    print(f"[+] Title : {title}")
    print(f"[+] HTML  : {html_path}")
    print(f"[+] Text  : {text_path}")
    print(f"[+] Text size: {len(text):,} characters")


def main():
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

    args = parser.parse_args()

    if not args.url.startswith(
        ("http://", "https://")
    ):
        print(
            "Error: URL must start with http:// or https://",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        extract(
            args.url,
            Path(args.output),
        )

    except requests.HTTPError as e:
        print(
            f"[!] HTTP error: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    except requests.RequestException as e:
        print(
            f"[!] Network error: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    except Exception as e:
        print(
            f"[!] Error: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()