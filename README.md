# canard-dl

Download articles and issues from [Le Canard Enchaîné](https://www.lecanardenchaine.fr).

## Modes

| Mode | Source | Account | Output |
|------|--------|---------|--------|
| Article | `lecanardenchaine.fr` | No | HTML + text |
| Issue | `lire.lecanardenchaine.fr` | Yes | PDF |

## Install

```sh
uv sync
```

## Article download

Download by URL:

```sh
uv run canard-dl "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Or list recent articles and pick one interactively:

```sh
uv run canard-dl --list
uv run canard-dl --list --section Économie
```

Each article is written to `output/` (override with `-o`) as `<slug>.html` and `<slug>.txt`.

Options:

- `-o, --output DIR` — output directory (default: `output`)
- `--list` — list recent articles and pick one to download
- `--section NAME` — restrict the list to one section
- `--days N` — only list articles from the last N days (default: 7)
- `-v, --verbose` — debug output
- `-q, --quiet` — only warnings and errors

## Issue download

Download a full digital issue as PDF (requires an account):

```sh
uv run canard-dl --download -e EMAIL -p PASSWORD
```

Or put your credentials in a `.env` file alongside the project root:

```env
CANARD_EMAIL=you@example.com
CANARD_PASSWORD=your-password
```

```sh
uv run canard-dl --download
```

Download a specific issue by number:

```sh
uv run canard-dl --download 5518
```

Options:

- `-e, --email` — account email (required)
- `-p, --password` — account password (required)
- `-o, --output DIR` — output directory (default: `output`)
- `--count N` — number of recent issues to list (default: 12)

## Development

```sh
uv sync
uv run pylint canard_dl
```
