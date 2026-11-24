# Contributing

To get started:

```sh
uv venv --python 3.11
uv pip install -e ".[dev]"
uv run pre-commit install
```

Run the checks:

```sh
uv run ruff format component_builder
uv run ruff check --select I --fix component_builder
uv run ruff check component_builder
uv run ty check
```

To version up using [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release):

```sh
uv run semantic-release version
```
