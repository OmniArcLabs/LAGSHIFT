# Contributing to LAGSHIFT

Thank you for helping improve LAGSHIFT. Keep changes focused, explain the user
impact, and include tests for behavior changes.

## Before opening a pull request

1. Install `requirements-dev.txt` with Python 3.12 on Windows.
2. Run `python -m unittest discover -s tests -q`.
3. Do not commit credentials, public IP addresses, private endpoints, diagnostic
   archives, build output, or user network state.
4. Preserve the public-edition boundary: no imported tunnel configurations,
   subscriptions, or general-purpose VPN surface.

Security vulnerabilities must be submitted through GitHub Private Vulnerability
Reporting rather than a public issue.
