# canard-dl

Download articles from [Le Canard Enchaîné](https://www.lecanardenchaine.fr).

## Usage

```sh
uv run python main.py "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Or, once installed:

```sh
uv pip install -e .
canard-dl "https://www.lecanardenchaine.fr/societe/54632-quand-la-croisiere-ne-s-amuse-pas"
```

Each article is written to `output/` (override with `-o`) as:

- `<slug>.html`
- `<slug>.txt`

Options:

- `-v, --verbose` — debug output
- `-q, --quiet` — only warnings and errors

## Development

```sh
uv sync
uv run python -X dev main.py "URL"
```
