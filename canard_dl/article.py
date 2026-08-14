"""Article extraction and cleanup from the Canard's HTML.

The article content is already present in the served HTML; the
paywall is purely CSS-based.
"""

import re

from bs4 import BeautifulSoup

UNWANTED_CLASSES = {
    "share-mobile",
    "share-sticky",
    "article__author",
    "article__tags",
    "list-breadcrumb",
    "modal",
}


def unlock_paywall(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove the CSS classes/IDs used to hide the article content.

    The content itself is already present in the HTML.
    """

    # <div id="paywall">
    for element in soup.find_all("div", id="paywall"):
        element.attrs.pop("id", None)
        element.attrs.pop("class", None)

    # <div class="paywall"> and <div class="non-paywall">
    for cls in ("paywall", "non-paywall"):
        for element in soup.find_all(
            "div",
            class_=lambda classes, cls=cls: classes and cls in classes,
        ):
            classes = (element.attrs or {}).get("class", [])
            classes = [
                c for c in classes
                if c != cls
            ]

            if classes:
                element["class"] = classes
            else:
                element.attrs.pop("class", None)

    return soup


def clean_article(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove everything that isn't useful article content."""

    # Remove scripts, styles and page navigation.
    for element in soup.find_all(
        ["script", "style", "nav", "header", "footer", "button", "form"]
    ):
        element.decompose()

    # Remove known non-article elements.
    for element in soup.find_all(class_=True):
        classes = set((element.attrs or {}).get("class", []))

        if classes & UNWANTED_CLASSES:
            element.decompose()

    return soup


def find_article(soup: BeautifulSoup) -> tuple[BeautifulSoup | None, BeautifulSoup | None]:
    """Find the article heading and body, with fallbacks."""

    heading = soup.find("div", class_="article__heading")
    editorial = soup.find("div", class_="editorial")

    if editorial is None:
        article = soup.find("article")

        if article is not None:
            return heading, article

    if heading is None:
        h1 = soup.find("h1")

        if h1 is not None:
            heading = h1.parent

    return heading, editorial


def extract_text(*elements: BeautifulSoup | None) -> str:
    chunks = []

    for element in elements:
        if element is None:
            continue

        text = element.get_text("\n", strip=True)

        if text:
            chunks.append(text)

    text = "\n\n".join(chunks)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def sanitize_html(*elements: BeautifulSoup | None) -> str:
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
                if attr not in {"href", "src", "class"}:
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