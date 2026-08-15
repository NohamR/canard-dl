# canard-dl

Download articles and issues from [Le Canard Enchaîné](https://www.lecanardenchaine.fr).

## Modes

| Mode | Source | Account | Output |
|------|--------|---------|--------|
| Article | `lecanardenchaine.fr` | No | HTML + text |
| Issue | `lire.lecanardenchaine.fr` | Yes | PDF |

## Install

```sh
git clone https://github.com/NohamR/canard-dl && cd canard-dl && uv sync
```

## Article download

Download by URL:

```sh
uv run canard-dl "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Or list recent articles and select one or more interactively:

```sh
uv run canard-dl --list
uv run canard-dl --list --section Économie
```

The interactive selector supports selecting multiple articles and a "Fetch older articles" action.

Each article is written to `output/` (override with `-o`) as `<slug>.html` and `<slug>.txt`.

Options:

- `-o, --output DIR` : output directory (default: `output`)
- `--list` : list recent articles and pick one to download
- `--section NAME` : restrict the list to one section
- `--days N` : only list articles from the last N days (default: 7)
- `-v, --verbose` : debug output
- `-q, --quiet` : only warnings and errors

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

You can choose the tile level with `--level` (recommended values are only `0`, `1`, or `2`; default is `0`):

```sh
uv run canard-dl --download --level 1
```

Download a specific issue by number:

```sh
uv run canard-dl --download 5518
```

Without an explicit issue number, the interactive selector lets you choose one or more issues and includes a "Fetch older issues" action.

Options:

- `-e, --email` : account email (required)
- `-p, --password` : account password (required)
- `-o, --output DIR` : output directory (default: `output`)
- `--count N` : number of recent issues to list (default: 12)
- `--level {0,1, 2}` : tile zoom level for issue download (default: 0)

## Development

```sh
uv sync
uv run pylint canard_dl
```
