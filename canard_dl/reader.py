"""PressView5 reader API — document/page metadata and tile download.

Handles fetching document metadata, page metadata, and downloading
tiles from pressview5.immanens.com.
"""

import io
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
from PIL import Image
from tqdm import tqdm

from canard_dl.logger import get_logger

logger = get_logger(__name__)

PV5_API = "https://pressview5.immanens.com/api"

TILE_SIZE = 512
DIVIDER = 2


@dataclass(frozen=True)
class RequestSettings:
    """Download metadata shared across page, tile, and issue requests."""

    level: int = 0
    is_double: bool = False
    token: str = ""
    mtime: int = 0


@dataclass(frozen=True)
class PageRequest:
    """Container for a page image download request."""

    publication_id: int
    document_id: int
    page_id: int
    width: int
    height: int
    settings: RequestSettings = RequestSettings()


@dataclass(frozen=True)
class TileRequest:
    """Container for a single tile request."""

    publication_id: int
    document_id: int
    page_id: int
    x: int
    y: int
    settings: RequestSettings = RequestSettings()


@dataclass(frozen=True)
class IssueRequest:
    """Container for an issue-wide download request."""

    publication_id: int
    document_id: int
    nb_pages: int
    settings: RequestSettings = RequestSettings()


def _headers(token: str = "") -> dict:
    base = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    }
    if token:
        base["x-access-token"] = token
    return base


def _url(path: str, token: str = "", mtime: int = 0) -> str:
    params = []
    if token:
        params.append(f"token={token}")
    if mtime:
        params.append(f"mt={mtime}")
    sep = "&" if "?" in path else "?"
    return f"{PV5_API}{path}{sep}{'&'.join(params)}" if params else f"{PV5_API}{path}"


def get_document(publication_id: int, document_id: int, token: str = "") -> dict:
    """Fetch document metadata."""

    url = f"{PV5_API}/document/{publication_id}/{document_id}"
    params = {}
    if token:
        params["token"] = token

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    doc = response.json()

    logger.debug(
        "Document %d/%d: %d pages, isDouble=%s, hasVecto=%s",
        publication_id,
        document_id,
        doc.get("nbPages", 0),
        doc.get("isDouble"),
        doc.get("hasVecto"),
    )

    return doc


def get_page(
    publication_id: int,
    document_id: int,
    page_id: int,
    *,
    mtime: int = 0,
    token: str = "",
) -> dict:
    """Fetch page metadata (width, height, number, etc.)."""

    url = f"{PV5_API}/document/{publication_id}/{document_id}/page/{page_id}"
    params = {}
    if token:
        params["token"] = token
    if mtime:
        params["mt"] = mtime

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    page = response.json()

    logger.debug(
        "Page %d: %dx%d, numbers=%s",
        page_id,
        page.get("width"),
        page.get("height"),
        page.get("number"),
    )

    return page


def compute_nb_levels(width: int, height: int) -> int:
    """Compute the number of zoom pyramid levels."""

    nb_levels = 1
    longest = max(width, height)

    while longest > TILE_SIZE:
        longest /= DIVIDER
        nb_levels += 1

    return nb_levels


def tile_grid(width: int, height: int, level: int = 0) -> tuple[int, int]:
    """Return (cols, rows) for the given zoom level."""

    scale = DIVIDER**level

    cols = math.ceil(width / (TILE_SIZE * scale))
    rows = math.ceil(height / (TILE_SIZE * scale))

    return cols, rows


def tile_url(request: TileRequest) -> str:
    """Build the URL for a single tile."""

    settings = request.settings
    p_id = request.page_id
    if settings.is_double and request.page_id != 1 and request.page_id % 2:
        p_id = request.page_id - 1

    path = (
        f"/document/{request.publication_id}/{request.document_id}"
        f"/page/{p_id}/tile/{request.x}/{request.y}/{settings.level}"
    )

    return _url(path, token=settings.token, mtime=settings.mtime)


def _download_tile(request: TileRequest, headers: dict[str, str]) -> tuple[int, int, bytes]:
    """Download one tile and return (row, col, payload)."""

    url = tile_url(request)
    logger.debug("Tile %d/%d: GET %s", request.x, request.y, url)

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return request.y, request.x, response.content


def _progress_info(progress: tqdm | None, message: str, *args: object) -> None:
    """Write info lines without breaking an active tqdm progress bar."""

    if progress is None:
        logger.info(message, *args)
        return

    text = message % args if args else message
    progress.write(f"INFO {text}")


# pylint: disable=too-many-locals
def download_page_tiles(
    request: PageRequest,
    *,
    progress: tqdm | None = None,
) -> list[list[bytes]]:
    """Download all tiles for a page at the given level.

    Returns a 2D list of tile image bytes: tiles[row][col].
    """

    settings = request.settings
    cols, rows = tile_grid(request.width, request.height, settings.level)

    _progress_info(
        progress,
        "Downloading page %d: %dx%d tiles at level %d",
        request.page_id,
        cols,
        rows,
        settings.level,
    )

    tile_requests = [
        TileRequest(
            publication_id=request.publication_id,
            document_id=request.document_id,
            page_id=request.page_id,
            x=col,
            y=row,
            settings=settings,
        )
        for row in range(rows)
        for col in range(cols)
    ]

    headers = _headers(settings.token)
    total_tiles = len(tile_requests)
    max_workers = min(16, max(1, total_tiles))
    logger.debug("Downloading %d tiles with %d workers", total_tiles, max_workers)

    by_coord: dict[tuple[int, int], bytes] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_download_tile, tile_request, headers)
            for tile_request in tile_requests
        ]
        for future in as_completed(futures):
            row, col, payload = future.result()
            by_coord[(row, col)] = payload
            if progress is not None:
                progress.update(1)

    return [[by_coord[(row, col)] for col in range(cols)] for row in range(rows)]


# pylint: disable=too-many-locals
def stitch_tiles(
    tiles: list[list[bytes]],
    page_width: int,
    page_height: int,
    *,
    level: int = 0,
) -> bytes:
    """Stitch tiles into a single JPEG image.

    Returns raw JPEG bytes.
    """

    img_width = math.ceil(page_width / DIVIDER**level)
    img_height = math.ceil(page_height / DIVIDER**level)

    canvas = Image.new("RGB", (img_width, img_height), "white")

    rows = len(tiles)
    cols = len(tiles[0]) if rows else 0

    for row in range(rows):
        for col in range(cols):
            tile_data = tiles[row][col]
            tile_img = Image.open(io.BytesIO(tile_data))

            x = col * TILE_SIZE
            y = row * TILE_SIZE

            canvas.paste(tile_img, (x, y))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95)

    return buf.getvalue()


def download_page_image(
    request: PageRequest,
    *,
    progress: tqdm | None = None,
) -> bytes:
    """Download and stitch all tiles for a page into a JPEG."""

    tiles = download_page_tiles(request, progress=progress)
    return stitch_tiles(tiles, request.width, request.height, level=request.settings.level)


def download_issue(request: IssueRequest) -> list[bytes]:
    """Download all pages of an issue as JPEG images.

    Returns a list of JPEG image bytes, one per page image.
    For double spreads, each image covers two logical pages.
    """

    pages: list[bytes] = []
    settings = request.settings

    if settings.is_double:
        page_nums = [1] + list(range(2, request.nb_pages + 1, 2))
    else:
        page_nums = list(range(1, request.nb_pages + 1))

    page_plan: list[tuple[int, dict]] = []
    total_tiles = 0

    for page_num in page_nums:
        page_meta = get_page(
            request.publication_id,
            request.document_id,
            page_num,
            mtime=settings.mtime,
            token=settings.token,
        )
        page_plan.append((page_num, page_meta))

        cols, rows = tile_grid(page_meta["width"], page_meta["height"], settings.level)
        total_tiles += cols * rows

    with tqdm(
        total=total_tiles,
        desc=f"Issue #{request.document_id} tiles",
        unit="tile",
    ) as progress:
        for idx, (page_num, page_meta) in enumerate(page_plan):

            img_data = download_page_image(
                PageRequest(
                    publication_id=request.publication_id,
                    document_id=request.document_id,
                    page_id=page_num,
                    width=page_meta["width"],
                    height=page_meta["height"],
                    settings=RequestSettings(
                        level=settings.level,
                        is_double=settings.is_double,
                        token=settings.token,
                        mtime=settings.mtime,
                    ),
                ),
                progress=progress,
            )

            pages.append(img_data)

            _progress_info(
                progress,
                "Page %d/%d done",
                idx + 1,
                len(page_nums),
            )

    return pages


def save_issue_pdf(
    pages: list[bytes],
    output_path: str,
) -> None:
    """Assemble JPEG page images into a PDF."""

    if not pages:
        logger.error("No pages to save")
        return

    images = []

    for page_data in pages:
        img = Image.open(io.BytesIO(page_data)).convert("RGB")
        images.append(img)

    first = images[0]
    rest = images[1:]

    first.save(
        output_path,
        "PDF",
        save_all=True,
        append_images=rest,
        resolution=300,
    )

    logger.info("Saved PDF: %s (%d pages)", output_path, len(pages))
