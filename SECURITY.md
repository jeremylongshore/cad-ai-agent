# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue.
2. Email the maintainer directly with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. Allow up to 72 hours for initial response.

## Security Design Principles

This tool follows these security principles:

- **Local-first**: DXF processing happens entirely on the user's machine.
- **No raw DXF editing by LLM**: The LLM planner returns structured operation JSON only. All edits are applied by deterministic local code.
- **Protected layers/blocks**: Configurable layers (default: `TITLE`, `TITLEBLOCK`, `SEAL`, `REVISION`) cannot be modified by any operation.
- **Save-as workflow**: Original DXF files are never overwritten.
- **No hardcoded secrets**: API keys are loaded from environment variables only.
- **Safe logging**: API keys and sensitive data are never written to logs.

## Dependency Security

- Dependencies are audited via `pip-audit` in CI.
- Static analysis via `bandit` runs on every PR.
- Dependency review via GitHub's `dependency-review-action` on PRs.
