# Development

## Commands

```bash
tox -e lint    # isort, black, flake8
tox -e test    # pytest with coverage
tox -e build   # build wheel + sdist

pytest                          # run tests directly
pytest tests/test_foo.py        # single file
pytest tests/ -k "event_parser" # filtered suite
```

## Config quirks

- Line length: **120** (black + flake8, see `setup.cfg` and `pyproject.toml`)
- Black ignores flake8's E203/W503 — do not "fix" those
- Pyright uses `venv/` (not `.venv/`); configured in `pyrightconfig.json`
- Source lives in `src/eth_pretty_events/`, not the repo root

## Dependencies

Core: `web3>=7.8`, `PyYAML`
Extras: `pytest` + `pytest-asyncio` + `factory_boy` (testing); `Flask` (flask); `google-cloud-pubsub` (pubsub); `Jinja2` (templates)

Install with: `pip install -e ".[testing,flask,pubsub]"`

## Environment

Required env vars (see `.env.sample`):
- `RPC_URL` — Ethereum RPC endpoint
- `ABI_PATHS` — space-separated ABI file directories
- `TEMPLATE_PATHS` — Jinja2 template directories
- `TEMPLATE_RULES` — YAML mapping event signatures to templates
- `ADDRESS_BOOK` — JSON map of addresses to names
- `CHAINS_FILE` — JSON chain metadata
- `BYTES32_RAINBOW` — JSON map of bytes32 role hashes to names
- `DISCORD_URL` — Discord webhook (for output)

## Architecture

- `cli.py` — CLI entrypoint (`pip install -e .` gives `script_name` command)
- `flask_app.py` — Flask app; receives Alchemy webhooks, validates signature
- `event_filter.py` — filters events by configurable rules
- `event_parser.py` — parses EVM events
- `render.py` / `jinja2_ext.py` — Jinja2 templating helpers
- `outputs.py` / `discord.py` / `print_output.py` / `pubsub.py` — output plugins (auto-loaded)
- `w3cache.py` — Web3 HTTP provider with retry/cache

## Testing

- Tests use **function-style** (e.g., `def test_foo():`), **not** class-based (`class Test:`)
