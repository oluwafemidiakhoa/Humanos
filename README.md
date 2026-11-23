# HumanityOS

**Mission:** Build autonomous AI workflows that perform useful work with evidence, consent and measurable outcomes.

This repository contains **v0.1 of the Opportunity Agent**: a local, authenticated Python API and deterministic, auditable opportunity-screening workflow. It is deliberately **not** an unrestricted agent, internet crawler, self-improving system, or production platform.

## Quick start

Requires Python 3.11+.

```powershell
cd C:\Users\adminidiakhoa\humanos
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:HUMANOS_API_KEY = "replace-with-a-long-random-secret"
python -m humanos
```

On Windows Command Prompt (cmd.exe), replace the environment-setting line with:

```cmd
set HUMANOS_API_KEY=replace-with-a-long-random-secret
```

Open http://127.0.0.1:8000/docs to explore the API. Send `Authorization: Bearer <your key>` to data endpoints. `GET /health` is public.

## Core workflow

1. `POST /v1/goals` — create a mission with keywords.
2. `POST /v1/candidates` — provide a potential opportunity and source URL.
3. `POST /v1/workers/run-once` — process up to 25 queued candidates.
4. `GET /v1/candidates` — inspect screening and limitations.
5. `POST /v1/candidates/{id}/decision` — record human approval or rejection.
6. `GET /v1/candidates/{id}/events` — inspect audit history.

**Current limitation:** screening checks keyword matches and HTTPS URL syntax, **not** verified eligibility, source truth or application status. Approval never submits anything.

## Verify locally

```powershell
python -m unittest discover -s tests -v
ruff check humanos tests
```

See [architecture](docs/architecture.md) for trust boundaries and next steps.
