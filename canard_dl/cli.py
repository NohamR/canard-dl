"""Command-line interface for canard-dl.

Two modes:
  - canard-dl <url>              Download an article (no account)
  - canard-dl --list             Pick an article from recent list
  - canard-dl --download           Download a full issue (account required)
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
from canard_dl.phenix import (
    generate_device_sign,
    get_anonymous_token,
    get_issues,
    get_publications,
    get_streaming_token,
    login,
)
from canard_dl.reader import (
    IssueRequest,
    RequestSettings,
    download_issue,
    get_document,
    save_issue_pdf,
)
from canard_dl.spoofer import fetch

logger = get_logger(__name__)

LE_CANARD_PUBLICATION_ID = 315


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


def _resolve_canard_publication(publications: list[dict]) -> dict:
    """Return the Le Canard publication, falling back to the first one."""

    for publication in publications:
        if publication.get("publication_id") == LE_CANARD_PUBLICATION_ID:
            return publication

    fallback = publications[0]
    logger.warning(
        "Le Canard not found, using %s",
        fallback.get("publication_title", "unknown"),
    )
    return fallback


def _select_issue(issues: list[dict], number: int | None) -> dict | None:
    """Return the chosen issue or prompt interactively if no number is supplied."""

    if number is not None:
        for issue in issues:
            if issue["number"] == number:
                return issue
        logger.error("Issue #%d not found", number)
        sys.exit(1)

    return _pick_issue(issues)


def _login(email: str, password: str) -> tuple[str, str]:
    """Authenticate to the service and return the user token and customer hash."""

    device_sign = generate_device_sign()
    logger.debug("device_sign: %s", device_sign)

    logger.info("Logging in...")
    login_data = login(email, password, get_anonymous_token(device_sign))
    logger.info("Logged in as %s", email)
    return login_data["x_user_token"], login_data["customer_hash"]


def _load_issue_download(args: argparse.Namespace) -> tuple[dict, str, dict] | None:
    """Fetch the selected issue, access token and document metadata."""

    user_token, customer_hash = _login(args.email, args.password)
    publications = get_publications(user_token, customer_hash, anonymous=False)

    if not publications:
        logger.error("No publications found")
        sys.exit(1)

    canard = _resolve_canard_publication(publications)
    issues = get_issues(canard["publication_id"], user_token, customer_hash, count=args.count)

    if not issues:
        logger.error("No issues found")
        sys.exit(1)

    issue = _select_issue(issues, args.number)
    if issue is None:
        return None

    logger.info(
        "Getting streaming token for #%d (%s)...",
        issue["number"],
        issue["display_date"],
    )
    access_token = get_streaming_token(
        issue["puc"],
        issue["number"],
        user_token,
        customer_hash,
    )

    doc = get_document(issue["puc"], issue["number"], token=access_token)
    logger.info("Downloading %d pages...", doc["nbPages"])
    return issue, access_token, doc


def cmd_download(args: argparse.Namespace) -> None:
    """Handle the 'download' subcommand — download a full issue."""

    issue_data = _load_issue_download(args)
    if issue_data is None:
        return

    issue, access_token, doc = issue_data
    output_dir = Path(args.output)
    pages = download_issue(
        IssueRequest(
            publication_id=issue["puc"],
            document_id=issue["number"],
            nb_pages=doc["nbPages"],
            settings=RequestSettings(
                is_double=doc.get("isDouble", False),
                token=access_token,
                mtime=doc.get("mtime", 0),
            ),
        )
    )

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
