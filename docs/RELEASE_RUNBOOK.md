# v0.3.0 release runbook

The release workflow is prepared but publishing is intentionally gated by
repository configuration. Do not create a tag until protected `main` contains
the intended commit and all required checks pass.

## One-time repository setup

1. Configure npm trusted publishing for `kingggg5/awe-tracegate`, workflow
   `.github/workflows/release.yml`, environment `npm`.
2. Configure PyPI trusted publishing for the same repository and workflow,
   environment `pypi`.
3. Protect `main`, require CI/CodeQL/dependency checks, and protect `npm` and
   `pypi` environments. Do not add long-lived registry tokens.

## Release sequence

```bash
git checkout main
git pull --ff-only origin main
git status --short
git tag --list 'v0.3.0'
git tag -a v0.3.0 -m "AWE TraceGate v0.3.0"
git push origin v0.3.0
```

The tag workflow verifies that the tag points at `origin/main`, runs the full
reusable CI workflow, rebuilds Python/npm/plugin/schema artifacts twice, checks
basenames and SPDX metadata, and clean-installs the resulting packages. npm
and PyPI publication are performed only after those checks succeed.

## Post-release verification

From a clean machine, download the release assets and run:

```bash
sha256sum --check SHA256SUMS
python -m venv .venv
.venv/bin/pip install awe_tracegate-0.3.0-py3-none-any.whl
.venv/bin/awe --version
npm install --ignore-scripts ./awe-tracegate-0.3.0.tgz
```

Record the tag, artifact hashes, install output, and Action SHA in the release
notes. If any registry or clean-install step fails, do not label the release
production-ready.
