# Security policy

## Supported versions

AWE TraceGate is pre-alpha. No release is currently guaranteed production
support or long-term security maintenance. Security fixes will target the latest
development version and the newest published pre-release when practical.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or include sensitive
trace data in a report.

Use GitHub private vulnerability reporting for this repository when available.
If that option is unavailable, contact the repository maintainer privately
through the contact method listed on the owner’s GitHub profile. Include:

- the affected version or commit;
- the smallest safe reproduction;
- expected and observed behavior;
- potential impact;
- suggested mitigation, if known.

Do not include live credentials, private customer data, or an exploit against a
system you do not own. Maintainers will acknowledge a usable report when
possible, investigate it, and coordinate disclosure according to severity and
available maintainer capacity. Pre-alpha status means response times are not an
SLA.

## In scope

Examples include:

- receipt canonicalization or digest bypass;
- a malformed trace producing an unintended `compiled` decision;
- dependency or binding confusion that crosses the documented safety gate;
- trace content causing code, command, network, or tool execution;
- API input bypassing the compiler’s typed validation;
- leakage of trace contents through default output or error handling.
- a bundled Skill or installer escaping the selected repository path, silently
  replacing an existing Skill, or weakening the documented evidence boundary.

## Out of scope

The following are limitations rather than vulnerabilities unless behavior
contradicts the documented contract:

- a compiled candidate being semantically poor or incomplete;
- lack of signer identity on an unsigned SHA-256 receipt;
- missing production controls on the local development API;
- denial of service that requires trusted local access and unrealistic input;
- unsupported runtime, browser, write-action, or autonomous-agent scenarios.

Treat Skill instructions as code during dependency review and pin the repository
revision before installing them. The bundled installers accept only the five
active Skill names, track managed file hashes, and refuse unmanaged or locally
modified Skill directories. Updates use staging and rollback; there is no force
overwrite mode. Neither Skill text nor agent output is trusted evidence.

See [docs/security.md](docs/security.md) for the full threat model and current
limitations.
