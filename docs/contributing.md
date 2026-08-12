# Contributing

Contributions are welcome — bug fixes, new features, documentation improvements, and examples.

## Quick Start

```bash
git clone https://github.com/vstorm-co/pydantic-deepagents.git
cd pydantic-deepagents
make install        # installs dependencies + pre-commit hooks
make test           # run the test suite
make all            # full check: format, lint, typecheck, security, tests
```

## Requirements for Every Pull Request

| Check | Command | Must pass? |
|-------|---------|-----------|
| Tests (100% coverage) | `make test` | **Required** |
| Ruff lint + format | `make lint` | **Required** |
| Pyright type checking | `make typecheck` | **Required** |
| MyPy strict type checking | `make typecheck-mypy` | **Required** |
| Bandit security scan | `make security` | **Required** |

All checks also run automatically in GitHub Actions on every push and pull request.

## Test Policy

New functionality **must** include tests. The `coverage fail_under = 100` setting in `pyproject.toml` enforces this — untested code causes `make test` to fail.

## Submitting a Pull Request

1. Fork the repository and create a branch from `main`
2. Make your changes, including tests for any new functionality
3. Run `make all` locally and ensure everything passes
4. Open a pull request with a clear description of the change and why it is needed

## Reporting Bugs & Requesting Features

- **Bug reports** — [open a GitHub Issue](https://github.com/vstorm-co/pydantic-deepagents/issues/new/choose) using the Bug Report template
- **Feature requests** — [open a GitHub Issue](https://github.com/vstorm-co/pydantic-deepagents/issues/new/choose) using the Feature Request template
- **Security vulnerabilities** — email **info@vstorm.co** (see [Security Policy](https://github.com/vstorm-co/pydantic-deepagents/blob/main/SECURITY.md))

## Full Guidelines

The complete contribution guide lives in [`CONTRIBUTING.md`](https://github.com/vstorm-co/pydantic-deepagents/blob/main/CONTRIBUTING.md) in the repository root, including coding standards, static analysis details, and the API documentation workflow.
