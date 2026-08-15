"""Command-line interface for canard-dl.

Two modes:
  - canard-dl <url>              Download an article (no account)
  - canard-dl --list             Pick an article from recent list
  - canard-dl download           Download a full issue (account required)
"""

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

    slug = re.sub(r"[^a-zA-Z0-9À-ÿ_-]+", "_", slug)
    return slug[:150]


def extract(url: str, output_dir: Path) -> None:
    """Download an article and write its HTML and text files."""

    logger.info("Downloading: %s", url)

    html = fetch(url)

    logger.info("Downloaded %s bytes", f"{len(html):,}")

    soup = BeautifulSoup(html, "html.parser")

    logger.debug("Unlocking CSS paywall")
    unlock_paywall(soup)

    logger.debug("Cleaning article")
    clean_article(soup)

    heading, editorial = find_article(soup)

    if not heading and not editorial:
        raise RuntimeError(
            "Could not find the article content. "
            "The site's HTML structure may have changed."
        )

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


def cmd_download(args: argparse.Namespace) -> None:
    """Handle the 'download' subcommand — download a full issue."""

    from canard_dl.phenix import (
        generate_device_sign,
        get_anonymous_token,
        get_publications,
        get_streaming_token,
        get_issues,
        login,
    )
    from canard_dl.reader import (
        download_issue,
        get_document,
        save_issue_pdf,
    )

    email = args.email
    password = args.password
    output_dir = Path(args.output)
    number = args.number

    # Step 1: device sign
    device_sign = generate_device_sign()
    logger.debug("device_sign: %s", device_sign)

    # Step 2: anonymous token
    anonymous_token = get_anonymous_token(device_sign)

    # Step 3: login
    logger.info("Logging in...")
    login_data = login(email, password, anonymous_token)
    user_token = login_data["x_user_token"]
    customer_hash = login_data["customer_hash"]
    logger.info("Logged in as %s", email)

    # Step 4: list publications
    publications = get_publications(user_token, customer_hash, anonymous=False)

    if not publications:
        logger.error("No publications found")
        sys.exit(1)

    # Find Le Canard publication (publication_id=315)
    canard = None
    for pub in publications:
        if pub.get("publication_id") == 315:
            canard = pub
            break

    if canard is None:
        # Fall back to first publication
        canard = publications[0]
        logger.warning(
            "Le Canard not found, using %s",
            canard.get("publication_title", "unknown"),
        )

    pub_id = canard["publication_id"]

    # Step 5: list issues
    issues = get_issues(
        pub_id,
        user_token,
        customer_hash,
        count=args.count,
    )

    if not issues:
        logger.error("No issues found")
        sys.exit(1)

    # If a specific number was given, find it
    if number is not None:
        issue = None
        for iss in issues:
            if iss["number"] == number:
                issue = iss
                break

        if issue is None:
            logger.error("Issue #%d not found", number)
            sys.exit(1)
    else:
        # Interactive picker
        issue = _pick_issue(issues)

        if issue is None:
            return

    # Step 6: streaming token
    logger.info(
        "Getting streaming token for #%d (%s)...",
        issue["number"],
        issue["display_date"],
    )
    access_token = get_streaming_token(
        pub_id,
        issue["puc"],
        user_token,
        customer_hash,
    )

    # Step 7: document metadata
    doc = get_document(pub_id, issue["puc"], token=access_token)

    # Step 8: download pages
    logger.info("Downloading %d pages...", doc["nbPages"])

    pages = download_issue(
        pub_id,
        issue["puc"],
        doc["nbPages"],
        is_double=doc.get("isDouble", False),
        token=access_token,
        mtime=doc.get("mtime", 0),
    )

    # Step 9: save PDF
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / f"canard-{issue['number']}.pdf"
    save_issue_pdf(pages, str(pdf_path))

    logger.info("Done: %s", pdf_path)


def _pick_issue(issues: list[dict]) -> dict | None:
    """Show issues and return the chosen one."""

    print()
    print("Available issues:")
    print()

    for i, issue in enumerate(issues, 1):
        print(
            f"{i:3}. #{issue['number']} — "
            f"{issue['display_date']} "
            f"({issue['pages']} pages)"
        )

    print()

    while True:
        try:
            choice = input(
                f"Pick an issue to download "
                f"(1-{len(issues)}, Enter to quit): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not choice:
            return None

        if choice.isdigit() and 1 <= int(choice) <= len(issues):
            return issues[int(choice) - 1]

        logger.warning("Invalid choice, try again")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Download articles and issues from Le Canard Enchaîné."
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
        "--download",
        nargs="?",
        const="",
        metavar="NUMBER",
        help="Download a full issue as PDF (account required, use -e/-p)",
    )

    parser.add_argument(
        "-e",
        "--email",
        help="Account email (required for --download)",
    )

    parser.add_argument(
        "-p",
        "--password",
        help="Account password (required for --download)",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="Number of recent issues to list (default: 12)",
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
    """Entry point."""

    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        if args.download is not None:
            if not args.email or not args.password:
                logger.error("--download requires -e EMAIL and -p PASSWORD")
                sys.exit(1)

            args.number = int(args.download) if args.download else None

            cmd_download(args)

        elif args.list:
            url = pick_article(section=args.section, days=args.days)

            if url:
                extract(url, Path(args.output))
        else:
            if not args.url or not args.url.startswith(("http://", "https://")):
                logger.error("URL must start with http:// or https://")
                sys.exit(1)

            extract(args.url, Path(args.output))

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
