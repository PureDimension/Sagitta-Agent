# Contributing to pydantic-deep

Thanks for your interest in contributing! Bug reports, enhancement proposals, and code contributions are all welcome. **All communication and contributions must be in English** so that maintainers and the wider community can review them effectively.

## Getting Help / Reporting Issues

- **Bug reports & feature requests** — [open a GitHub Issue](https://github.com/vstorm-co/pydantic-deepagents/issues)
- **Security vulnerabilities** — email **info@vstorm.co** (do NOT use public Issues; see [SECURITY.md](SECURITY.md))
- **Questions & discussion** — GitHub Issues are the primary discussion channel and are publicly searchable

All issues and pull requests are archived publicly on GitHub and can be referenced by URL.

## Development Setup

```bash
git clone https://github.com/vstorm-co/pydantic-deepagents.git
cd pydantic-deepagents
make install
```

Prerequisites: [uv](https://github.com/astral-sh/uv) (Python package manager) and [pre-commit](https://pre-commit.com/).

## Running Tests

The automated test suite uses [pytest](https://pytest.org/) and can be invoked in the standard way:

```bash
pytest                   # standard pytest invocation
make test                # run tests with coverage report
make all                 # lint + typecheck + security scan + test
```

Run specific tests:

```bash
# Single test function
uv run pytest tests/test_agent.py::test_function_name -v

# Single test file
uv run pytest tests/test_agent.py -v

# With debug output
uv run pytest tests/test_agent.py -v -s
```

## Coding Standards

All code must conform to the standards defined in [`pyproject.toml`](pyproject.toml). The full configuration lives there; the key tools are:

| Tool | Purpose | Run with |
|------|---------|---------|
| [Ruff](https://github.com/astral-sh/ruff) | Linting + formatting (E, F, I, UP, B, SIM, Q, C90 rules) | `make lint` |
| [Pyright](https://github.com/microsoft/pyright) | Static type checking | `make typecheck` |
| [MyPy](https://mypy.readthedocs.io/) | Strict static type checking | `make typecheck-mypy` |
| [Bandit](https://bandit.readthedocs.io/) | Security-focused static analysis | `make security` |
| [Codespell](https://github.com/codespell-project/codespell) | Spell checking | via `pre-commit` |

All of these tools are FLOSS. The project can be built, tested, and checked using only free and open-source software.

## Requirements for Acceptable Contributions

All pull requests **must** satisfy the following before merging:

- **100% test coverage** — no exceptions (`make test` enforces this via `coverage fail_under = 100`)
- **Pass Pyright** — `make typecheck`
- **Pass MyPy** — `make typecheck-mypy`
- **Pass Ruff** — `make lint` (formatting + linting)
- **Pass Bandit** — `make security` (no unresolved medium/high severity findings)
- **Pass all CI checks** — the GitHub Actions pipeline must be green

## Test Policy

> **As major new functionality is added to the project, tests of that functionality MUST be added to the automated test suite.**

This is enforced mechanically: `coverage fail_under = 100` in `pyproject.toml` means that untested code causes `make test` to fail. There are no exceptions. If you add a function, add a test. If you add a branch, test both sides.

Use `# pragma: no cover` only for genuinely untestable code (e.g., platform-specific branches that cannot be reached in the test environment). Maintainers will ask for justification on every `pragma: no cover` annotation during review.

## Quick Reference

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies + pre-commit hooks |
| `make test` | Run tests with coverage |
| `make lint` | Run Ruff (format + lint) |
| `make typecheck` | Run Pyright |
| `make typecheck-mypy` | Run MyPy |
| `make security` | Run Bandit security scanner |
| `make all` | Run all checks |
| `make docs-serve` | Serve docs locally at http://localhost:8000 |

## Static Analysis & Security

We run multiple layers of static analysis on every commit and in CI:

- **Ruff** — catches bugs, code style issues, and common anti-patterns
- **Pyright / MyPy** — strict type checking eliminates entire categories of runtime errors
- **Bandit** — security-focused scanner that checks for common Python security issues (e.g., unsafe subprocess usage, SQL injection patterns, insecure random number generation)

Medium- and high-severity Bandit findings block merges. Any finding that is a false positive must be marked with a `# nosec` comment and a justification.

## API Documentation

The external interface of the library is documented in the [API Reference](https://vstorm-co.github.io/pydantic-deepagents/api/). When adding or changing public APIs, update the docstrings — the API reference is auto-generated from them via `mkdocstrings`.

## Pull Request Process

1. Fork the repo and create your branch from `main`
2. Make your changes, **including tests** for any new functionality
3. Ensure `make all` passes locally before pushing
4. Submit a PR with a clear description of what changed and why
5. The PR title should follow the [Conventional Commits](https://www.conventionalcommits.org/) style (`feat:`, `fix:`, `docs:`, etc.)
6. A maintainer will review and merge; PRs are typically reviewed within a few business days

## Questions?

Open an issue on [GitHub](https://github.com/vstorm-co/pydantic-deepagents/issues).
