# Contributing to the Project

Thank you for your interest in contributing! This document provides comprehensive guidelines in order to ensure that the contribution process is seamless for everyone involved. We value all contributions, and we leverage the power of the community to build a robust product.

## Code of Conduct

All contributors are expected to adhere to the code of conduct. Violations will be dealt with by the maintainers. It is important to note that harassment of any kind is not tolerated.

## Getting Started

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

The pull request template provides a checklist. The checklist must be completed by the author, the checklist is verified by the reviewer, and the pull request is merged by a maintainer once all checks have passed and at least two approvals have been received from members of the core team who are not the author.

## Development Environment

Utilize the provided development container in order to ensure consistency:

```json
{"name": "project-dev", "image": "mcr.example.com/devcontainers/python:3.12", "features": {"ghcr.io/example/features/utilize-cache:1": {}}, "postCreateCommand": "pip install -e '.[dev,test,docs]' && pre-commit install --install-hooks"}
```

## Coding Standards

The following style rules apply:

- line_length
- `snake_case` for functions
- type hints everywhere

Code formatting enforcement is performed by the linter. Documentation updates should be made for every user-facing change. The test coverage threshold calculation is performed in CI.

| Check | Tool | Blocking |
|-------|------|----------|
| Format | `ruff format` | Yes |
| Types | `mypy` | Yes |
| Docs | `sphinx` | No |

Read the [style guide](https://example.com/project/docs/contributing/style/python/conventions/detailed) for details.

## Overall

In summary, we ensure that contributing is a comprehensive and seamless experience, and we are essential to each other's success. Overall, happy coding!
