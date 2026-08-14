# canard-dl

Download articles from [Le Canard Enchaîné](https://www.lecanardenchaine.fr).

## Usage

```sh
uv run main.py "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Or, once installed:

```sh
uv pip install -e .
canard-dl "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Pick an article from the latest list instead of pasting a URL:

```sh
uv run main.py --list
```

Each article is written to `output/` (override with `-o`) as:

- `<slug>.html`
- `<slug>.txt`

Options:

- `--list` — list recent articles and pick one to download
- `--section <name>` — restrict the list to one section
- `--days <n>` — only list articles from the last n days (default: 7)
- `-v, --verbose` — debug output
- `-q, --quiet` — only warnings and errors

## Development

```sh
uv sync
uv run python -X dev main.py "URL"
```
