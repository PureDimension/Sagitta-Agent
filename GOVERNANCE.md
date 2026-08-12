# Governance

This document describes the governance model for **pydantic-deep**.

## Maintainers

| Name | GitHub | Organization | Role |
|------|--------|-------------|------|
| Kacper Włodarczyk | [@DEENUU1](https://github.com/DEENUU1) | [Vstorm](https://vstorm.co) | Lead Maintainer |
| Dawid Woleek | [@Woleek](https://github.com/Woleek) | [Vstorm](https://vstorm.co) | Core Maintainer |

## Decision Making

Technical decisions are made by the lead maintainer with input from core maintainers and the community via GitHub Issues and Pull Requests. Decisions are made asynchronously — there are no required meetings.

All changes to the codebase must pass the CI quality gates:
- 100% test coverage
- Pyright strict mode (zero type errors)
- MyPy strict mode (zero type errors)
- Ruff linting (zero violations)

For significant architectural changes, an Issue is opened first to allow community discussion before implementation begins.

## Becoming a Maintainer

Contributors who have demonstrated sustained engagement with the project may be nominated as maintainers. The criteria for nomination:

- 5 or more merged Pull Requests with meaningful contributions
- Familiarity with the project's architecture, coding standards, and CI requirements
- Active participation in Issue and PR discussions

Nominations are made by existing maintainers via a GitHub Issue. Approval requires a simple majority of current maintainers. New maintainers are added to this document and granted repository write access.

## Removing a Maintainer

A maintainer may step down voluntarily by opening a PR to update this document. Maintainers who have been inactive for 12 months may be moved to Emeritus status by a simple majority vote of active maintainers.

## Emeritus Maintainers

Emeritus maintainers are former maintainers who are no longer actively contributing. They are recognized for their past contributions and may return to active status at any time.

| Name | GitHub |
|------|--------|
| — | — |

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold this standard. Violations may be reported to the maintainers via the contact information in the repository.

## Changes to This Document

Changes to this governance document require a Pull Request and approval from the lead maintainer. Significant changes (e.g., changing the decision-making process) should be announced via a GitHub Issue to allow community input before merging.
