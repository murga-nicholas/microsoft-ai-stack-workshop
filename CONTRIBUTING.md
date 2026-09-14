# Contributing and quality gates

This repository favours small, explicit modules over framework magic. Keep every
example easy to explain from a stage, and hold every change to the same automated
checks as production code.

## Set up

```powershell
Copy-Item .env.example .env
uv sync --frozen --group legacy
```

```bash
cp .env.example .env
uv sync --frozen --group legacy
```

Run every command from the repository root. `.env.example` documents every variable
this project's own code reads and is the only one of the two files that is tracked.

`uv.lock` is authoritative. Add or update dependencies with `uv`, then commit the
matching `pyproject.toml` and lockfile changes together.

## Required checks

```bash
uv run ruff format --check src/ tests/ deck/
```

```bash
uv run ruff check src/ tests/ deck/
```

```bash
uv run mypy
```

```bash
uv run pytest --cov=msai_demo --cov-report=term-missing
```

```bash
uv lock --check
```

Use `uv run ruff format src/ tests/ deck/` and `uv run ruff check --fix src/ tests/ deck/` for
safe mechanical fixes. Review the resulting diff; automated fixes do not replace
judgment.

## Adding a technology

Read [`docs/module_spec.md`](docs/module_spec.md) first — it is the contract, not a
suggestion. In short:

1. One module under `src/msai_demo/`, one public `async def run_<name>_demo(...)`.
2. Return a `contracts.DemoResult`. Pick the `mode` that is **true**, not the one
   that looks best.
3. Put the external call behind a `Protocol` and inject it, so the test suite uses a
   fixture adapter and never a mock of the framework.
4. Add one row to `DEMOS` in `cli.py` and one row to `LIVE_REQUIREMENTS` in
   `doctor.py`.
5. Add `tests/test_<name>_demo.py` and take the module to 100% statements and
   branches.
6. Add the slide, and the entry in the README table.

## Coding conventions

- Keep Python within 79 columns, docstrings within 72, so it satisfies PEP 8 and
  Google's 80-column ceiling.
- Google-style docstrings on every public API and every non-obvious private helper.
- Type public inputs and outputs. Keep `Any` at SDK boundaries and convert it into a
  local `TypedDict`, `Protocol` or concrete type immediately.
- Import optional SDKs **inside** the function. A missing package must be a reported
  mode, not an `ImportError` at startup.
- Never print a credential value, and never commit a `.env`.
- Keep tests offline. Live provider runs belong in the documented presentation
  workflow, not in the suite.
- Console output stays ASCII: Windows terminals default to a legacy code page and
  turn an em dash into a replacement character.

## Honesty rules

These are the ones that matter most, because this repository's whole argument is that
its output can be trusted.

- **Never widen a claim to make a demo look better.** If the SDK is not installed,
  say `sdk_invoked: false`. If the response was synthetic, name the fixture.
- **A blocked call is a result, not a failure.** A real 403 is
  `mode="live_service"`, `status="blocked"`. Do not catch it and return `ok`.
- **Never invent a zero.** Missing token usage is `None`.
- **Do not compare a framework against a straw man.** The AutoGen lane must be
  written as well as the Agent Framework lane; the comparison is about ownership of
  integration code, and it is measured, not asserted.
- If you add a claim about an external product, add it to
  [`docs/research.md`](docs/research.md) with a dated source.

## The deck

```bash
uv run --group deck python deck/collect_facts.py
```

```bash
uv run --group deck python deck/build_deck.py
```

Slide numbers come from the `SLIDES` tuple in `build_deck.py`; never type one into a
slide. Quoted figures come from `deck/facts.py`, which reads the installed packages
and `deck/facts.json`. The build fails if any shape overflows the safe area or if a
text box is too small for its text — layout is a test.
