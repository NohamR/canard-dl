"""PressView5 reader API — document/page metadata and tile download.

Handles fetching document metadata, page metadata, and downloading
tiles from pressview5.immanens.com.
"""

import math

from canard_dl.logger import get_logger

logger = get_logger(__name__)

PV5_API = "https://pressview5.immanens.com/api"

TILE_SIZE = 512
DIVIDER = 2


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
    return f"{PV5_API}{path}{sep}{','.join(params)}" if params else f"{PV5_API}{path}"


def get_document(publication_id: int, document_id: int, token: str = "") -> dict:
    """Fetch document metadata."""

    url = f"{PV5_API}/document/{publication_id}/{document_id}"

    import requests

    response = requests.get(
        url,
        headers=_headers(token),
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
    is_double: bool = False,
    mtime: int = 0,
) -> dict:
    """Fetch page metadata (width, height, number, etc.)."""

    server_id = _server_id(page_id, is_double)

    url = f"{PV5_API}/document/{publication_id}/{document_id}/page/{server_id}"
    if mtime:
        url += f"?mt={mtime}"

    import requests

    response = requests.get(
        url,
        headers=_headers(),
        timeout=30,
    )

    response.raise_for_status()

    page = response.json()

    logger.debug(
        "Page %d (server_id=%d): %dx%d, numbers=%s",
        page_id,
        server_id,
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


def _server_id(page_id: int, is_double: bool) -> int:
    """Map a logical page number to the server image id."""

    if is_double and page_id != 1 and page_id % 2:
        return page_id - 1

    return page_id


def tile_url(
    publication_id: int,
    document_id: int,
    page_id: int,
    x: int,
    y: int,
    level: int,
    *,
    is_double: bool = False,
    token: str = "",
    mtime: int = 0,
) -> str:
    """Build the URL for a single tile."""

    server_id = _server_id(page_id, is_double)

    path = (
        f"/document/{publication_id}/{document_id}"
        f"/page/{server_id}/tile/{x}/{y}/{level}"
    )

    return _url(path, token=token, mtime=mtime)


def download_page_tiles(
    publication_id: int,
    document_id: int,
    page_id: int,
    width: int,
    height: int,
    *,
    is_double: bool = False,
    token: str = "",
    mtime: int = 0,
    level: int = 0,
) -> list[list[bytes]]:
    """Download all tiles for a page at the given level.

    Returns a 2D list of tile image bytes: tiles[row][col].
    """

    import requests

    cols, rows = tile_grid(width, height, level)

    logger.info(
        "Downloading page %d: %dx%d tiles at level %d",
        page_id,
        cols,
        rows,
        level,
    )

    tiles: list[list[bytes]] = []

    for row in range(rows):
        row_tiles: list[bytes] = []

        for col in range(cols):
            url = tile_url(
                publication_id,
                document_id,
                page_id,
                col,
                row,
                level,
                is_double=is_double,
                token=token,
                mtime=mtime,
            )

            logger.debug("Tile %d/%d: GET %s", col, row, url)

            response = requests.get(
                url,
                headers=_headers(token),
                timeout=30,
            )

            response.raise_for_status()

            row_tiles.append(response.content)

        tiles.append(row_tiles)

    return tiles


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

    from PIL import Image
    import io

    # Determine the actual image dimensions after scaling
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

            # Edge tiles may extend beyond the canvas
            canvas.paste(tile_img, (x, y))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95)

    return buf.getvalue()


def download_page_image(
    publication_id: int,
    document_id: int,
    page_id: int,
    width: int,
    height: int,
    *,
    is_double: bool = False,
    token: str = "",
    mtime: int = 0,
    level: int = 0,
) -> bytes:
    """Download and stitch all tiles for a page into a JPEG."""

    tiles = download_page_tiles(
        publication_id,
        document_id,
        page_id,
        width,
        height,
        is_double=is_double,
        token=token,
        mtime=mtime,
        level=level,
    )

    return stitch_tiles(tiles, width, height, level=level)


def download_issue(
    publication_id: int,
    document_id: int,
    nb_pages: int,
    *,
    is_double: bool = False,
    token: str = "",
    mtime: int = 0,
) -> list[bytes]:
    """Download all pages of an issue as JPEG images.

    Returns a list of JPEG image bytes, one per logical page.
    """

    pages: list[bytes] = []

    for page_num in range(1, nb_pages + 1):
        page_meta = get_page(
            publication_id,
            document_id,
            page_num,
            is_double=is_double,
            mtime=mtime,
        )

        img_data = download_page_image(
            publication_id,
            document_id,
            page_num,
            page_meta["width"],
            page_meta["height"],
            is_double=is_double,
            token=token,
            mtime=mtime,
        )

        pages.append(img_data)

        logger.info("Page %d/%d done (%d bytes)", page_num, nb_pages, len(img_data))

    return pages


def save_issue_pdf(
    pages: list[bytes],
    output_path: str,
) -> None:
    """Assemble JPEG page images into a PDF."""

    from PIL import Image
    import io

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
