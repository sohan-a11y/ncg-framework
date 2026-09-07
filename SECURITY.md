# Security Policy

## Scope

NCG Framework is a research/educational tool for studying AI-guided password generation and hardware-accelerated verification. It is **not intended for use against systems you do not own or lack explicit authorization to test.** Misuse reports (i.e. reports that someone used this tool against a system without authorization) are a matter for the platform/service that was targeted, not a "vulnerability" in this project — please don't file those here.

This policy covers actual vulnerabilities *in the project itself*: e.g. a flaw that lets untrusted input reach `eval`/`exec`, a path-traversal issue in file loading, a dependency with a known CVE, or a flaw in the SHA-256 implementation that produces incorrect digests.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report them using [GitHub's private security advisory feature](https://github.com/sohan-a11y/ncg-framework/security/advisories/new). This keeps the report visible only to maintainers until a fix is ready.

When submitting, please include:

- A clear description of the vulnerability
- Steps to reproduce (a minimal script or CLI command is ideal)
- The potential impact
- Your assessment of severity (critical / high / medium / low)

## Response Timeline

| Milestone | Target |
|-----------|--------|
| Acknowledge receipt | Within 5 business days (this is a small, unfunded research project — response times are best-effort) |
| Confirm or dispute | Within 2 weeks |
| Patch released | Best-effort; critical issues prioritized |

## Known Limitations (not vulnerabilities, but worth knowing)

- The hardware RTL has not been synthesized or run through Verilator co-simulation — do not treat it as production-ready.
- The bundled/demo model checkpoints are trained on small synthetic datasets and should not be assumed to generalize to real-world password distributions.
