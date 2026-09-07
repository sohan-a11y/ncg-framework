# Contributing to NCG Framework

Thanks for your interest in improving NCG. This document covers everything you need to get started.

## Ways to Contribute

- **Bug reports** — open an issue with steps to reproduce and your environment (`ncg doctor` output is helpful)
- **Feature requests** — open an issue describing the use case, not just the feature
- **Code** — see the workflow below
- **Documentation** — fix typos, add examples, improve explanations
- **Hardware** — RTL co-simulation (Verilator), synthesis validation, and equivalence testing against `hardware/python_sim.py` are especially welcome; see [Hardware Status](README.md#hardware-status) for what's still open

## Development Setup

```bash
git clone https://github.com/sohan-a11y/ncg-framework.git
cd ncg-framework
pip install -e ".[dev]"
ncg doctor
pytest tests/ -v
```

## Code Style

- **Formatter/linter:** `ruff check software/` and `ruff format software/` — zero warnings expected
- **Type checking:** `mypy software/` — type hints required on public functions
- **Tests:** `pytest tests/ -v` — new functionality needs test coverage; see `tests/test_context_conditioning.py` for the expected style (deterministic assertions over sampling-dependent ones where possible — sampling-based tests are prone to flakiness on small models)

## Before Opening a PR

```bash
pytest tests/ -v
ruff check software/
mypy software/
```

All three should pass. If you touch RTL (`hardware/*.sv`), also run Verilator lint:

```bash
verilator --lint-only -Wall --top-module <module_name> hardware/<path>/<file>.sv
```

## Commit Style

Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. Keep the subject line under 72 chars; explain *why* in the body when the change isn't self-evident from the diff.

## Adding a New Hardware Module

1. Write the RTL under `hardware/`.
2. Add a matching, cycle-accurate Python model to `hardware/python_sim.py` (see its docstring — the Python model is treated as the executable specification).
3. Cross-validate the Python model against a known-good reference (NIST vectors, `hashlib`, or algebraic invariants) in `tests/test_hardware_python_sim.py`.
4. Verilator-lint the RTL and note the result in your PR description.

## Reporting Security Issues

Do not open a public issue for security vulnerabilities — see [SECURITY.md](SECURITY.md).
