# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An `AGENTS.md` already exists at repo root with the canonical operating guide (start-here links, do/don't list). Read it — this file adds commands and architecture detail rather than repeating it.

## Commands

```bash
# Run local chat API (Terminal 1) — requires USE_BEDROCK=true + BEDROCK_MODEL_ID
# (reads them from repo-root .env if present; no mock mode exists anymore)
python scripts/local_api.py

# Run UI dev server (Terminal 2)
cd ui && npm install && npm run dev
# -> http://127.0.0.1:5173, Vite proxies /chat to the local API

# Full unit suite
python -m unittest discover -s lambda/tests -v

# Single test
python -m unittest lambda.tests.test_tools.CampusAssistTests.test_off_topic

# UI build / preview
cd ui && npm run build
cd ui && npm run preview

# Agent CLI smoke test (no AgentCore SDK required)
python -m agent.main "What is the minimum attendance for semester exams?"

# Teardown deployed AWS stack
./scripts/teardown.sh
```

There is no lint config in this repo (no ruff/eslint config files) — don't assume one.

## Architecture

Request path: browser UI -> API Gateway (`infra/template.yaml`, `HttpApi` + `/chat`) -> `lambda/invoke/handler.py`, which routes on whether `AGENT_RUNTIME_ARN` is set:
- **Set** -> `invoke_agentcore()` calls `bedrock-agentcore.invoke_agent_runtime` against the deployed AgentCore Runtime (`agent/main.py` entrypoint). Not currently deployed in prod, so this branch is dead in the live stack today but is what `agent/main.py`'s AgentCore Runtime path is for.
- **Unset (current live path)** -> imports `campus_logic.run_campus_assist` and runs entirely in the invoke Lambda's own process.

There is no mock mode anymore (`mock_chat` was removed) — `run_campus_assist` always requires `USE_BEDROCK=true` and calls Bedrock Converse with primary `us.anthropic.claude-haiku-4-5-20251001-v1:0` and backup `us.amazon.nova-lite-v1:0`. If both fail, the raw exception text becomes the `reply`. Every response carries a `mode` field: `off-topic`, `error`, `live-bedrock`, or `agentcore`.

Response contract: `{ reply, citations, toolsUsed, sessionId, mode }`.

**Three sets of files are duplicated on disk and must be kept in sync by hand** — SAM's `CodeUri` for `InvokeFunction` is `lambda/invoke/`, so anything that Lambda imports or reads at runtime has to physically live inside that directory; there is no build/bundle step that copies files in for you:
- `agent/campus_logic.py` == `lambda/invoke/campus_logic.py` (same file, byte-for-byte) — `agent/` is the AgentCore Runtime copy, `lambda/invoke/` is the packaging copy the live Lambda actually imports.
- `lambda/tools/handlers.py` == `lambda/invoke/handlers.py` — tool logic (`get_admission_deadline`, `get_exam_schedule`, `create_ticket`). Tests import from `lambda/tools/handlers.py`.
- `docs/kb/**/*.md` == `lambda/invoke/kb/**/*.md` — the knowledge base. `campus_logic._search_kb` is a keyword match over these markdown files at request time; this is not a real Bedrock Managed Knowledge Base / vector store, despite `DocsBucket` existing in S3 for it.

Infra (`infra/template.yaml`, SAM): `InvokeFunction` (the `/chat` API, env vars `AGENT_RUNTIME_ARN`, `USE_BEDROCK`, `BEDROCK_MODEL_ID`, `BEDROCK_FALLBACK_MODEL_ID`, includes an `aws-marketplace:Subscribe/Unsubscribe/ViewSubscriptions` IAM statement because Nova Lite is Marketplace-listed), three standalone tool Lambdas (`AdmissionDeadlineFunction`, `ExamScheduleFunction`, `CreateTicketFunction` — deployed but not wired to anything over the network; the invoke path calls the Python functions in-process instead), a private `DocsBucket`, and a public `UiBucket` (S3 static website hosting — the HTTP fallback added because CloudFront distribution creation is blocked pending AWS account verification). Target account: `390403887579` (IAM `zuber`).

AgentCore deploy is direct-code (no Docker), driven by `agent/agentcore.yaml` + `agentcore deploy` run from `agent/`.

`.planning/` contains phase-by-phase deployment notes and the current as-built state (`.planning/12-REQUIREMENTS.md` has the full AWS-services-used breakdown) — check there for why specific infra/CI choices were made before changing `infra/template.yaml` or `.github/workflows/`.

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed execution, observability, and audit logging. If unavailable, use the AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with `retrieve_skill` and prefer its guidance over general knowledge.
- When uncertain about specific AWS details (API parameters, permissions, limits, error codes), verify against documentation rather than guessing. State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework principles.
- Do not use em dashes in AWS resource names or descriptions. Use hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret, credential, API key, token, or password task. MUST NOT call `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST NOT hit the Secrets Manager Agent daemon directly. MUST use `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with `asm-exec` so the secret resolves at runtime without entering context.
