# canard-dl

Download articles from [Le Canard Enchaîné](https://www.lecanardenchaine.fr).

The article's premium content is already present in the served HTML —
the paywall is purely CSS-based — so no login is required. We fetch the
page as Googlebot (the site serves full content to Google for
indexing), unlock the CSS paywall, and export the article as clean HTML
and text.

The Googlebot spoofer is inspired by the official
[Calibre recipe](https://github.com/debian-calibre/calibre/blob/37ec650f9dd717c235c96344eea74970959781b2/recipes/le_canard_enchaine.recipe#L24).

## Usage

```sh
uv run python main.py "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Or, once installed:

```sh
uv pip install -e .
canard-dl "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

For each article, two files are written to `output/` (override with
`-o`):

- `<slug>.html` — a standalone, minimal HTML page
- `<slug>.txt` — plain text

Logging goes to stderr and can be tuned with:

- `-v, --verbose` — debug output (timestamps, module names, HTTP details)
- `-q, --quiet` — only warnings and errors

## Development

```sh
uv sync
uv run python -X dev main.py "URL"
```

## How it works

1. **Spoofer** (`canard_dl/spoofer.py`): request the article as
   Googlebot.
2. **Unlock** (`canard_dl/article.py`): strip the `paywall` /
   `non-paywall` classes and `#paywall` id, then drop navigation,
   scripts and other non-article elements.
3. **Extract** (`canard_dl/cli.py`): locate the article heading and
   body, and export them as HTML and text.