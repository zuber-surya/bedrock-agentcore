# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An `AGENTS.md` already exists at repo root with the canonical operating guide (start-here links, do/don't list). Read it — this file adds commands and architecture detail rather than repeating it.

## Commands

```bash
# Run local mock chat API (Terminal 1)
python scripts/local_api.py

# Run UI dev server (Terminal 2)
cd ui && npm install && npm run dev
# -> http://127.0.0.1:5173, Vite proxies /chat to the mock API

# Full unit suite
python -m unittest discover -s lambda/tests -v

# Single test
python -m unittest lambda.tests.test_tools.ToolTests.test_admission_deadline_btech

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

Request path: browser UI -> API Gateway (`infra/template.yaml`, `HttpApi` + `/chat`) -> `lambda/invoke/handler.py` -> either local mock logic or Bedrock AgentCore Runtime (`bedrock-agentcore.invoke_agent_runtime`) -> `agent/main.py` entrypoint -> Bedrock Converse + KB + tool Lambdas.

Response contract everywhere is `{ reply, citations, toolsUsed, sessionId }` — enforced by both `lambda/invoke/handler.py` and `agent/campus_logic.py`.

**Two independent implementations of the same chat brain exist and must be kept in sync by hand:**
- `lambda/invoke/handler.py::mock_chat` / `_search_kb` — used when `MOCK_MODE=true` or no `AGENT_RUNTIME_ARN` is set (the API Gateway path never reaches AgentCore in this case).
- `agent/campus_logic.py::run_campus_assist` / `gather_context` — used by the actual AgentCore runtime entrypoint (`agent/main.py`), and optionally calls Bedrock Converse (`bedrock_generate`) when `USE_BEDROCK=true` and `BEDROCK_MODEL_ID` is set.

Both re-implement the same off-topic filter, keyword-based KB search over `docs/kb/**/*.md`, and tool-triggering keyword lists. When changing chat behavior (new keywords, new answer text, new off-topic rules), update both files or they will silently diverge. `lambda/invoke/handler.py` also has a `_builtin_hits` fallback used only if `docs/kb` isn't packaged alongside the Lambda.

**Tool handlers are duplicated too**: `lambda/tools/handlers.py` and `lambda/invoke/handlers.py` (plural, sibling of `handler.py` singular) are byte-for-byte identical copies of `get_admission_deadline`, `get_exam_schedule`, `create_ticket`, and the `handler_*` Lambda wrappers. `lambda/invoke/handler.py` imports from whichever resolves first (`handlers` then falls back to `tools.handlers`) depending on how the Lambda is packaged/zipped. `agent/campus_logic.py` always imports from `lambda/tools/handlers.py` directly (via `sys.path` manipulation in `agent/main.py`). Tests (`lambda/tests/test_tools.py`) import from `lambda/tools/handlers.py`. If you change tool logic, change `lambda/tools/handlers.py` and mirror it into `lambda/invoke/handlers.py`.

Infra (`infra/template.yaml`, SAM): defines `InvokeFunction` (the `/chat` API), three standalone tool Lambdas (`AdmissionDeadlineFunction`, `ExamScheduleFunction`, `CreateTicketFunction` — these exist as separate deployable functions but are not currently wired to anything invoking them over the network; the invoke path calls the Python functions in-process instead), and a private `DocsBucket` for KB docs. CloudFront/S3 UI hosting is deferred (see git history / `.planning/`) — UI is currently run locally against the API Gateway endpoint via `VITE_API_URL`.

AgentCore deploy is direct-code (no Docker), driven by `agent/agentcore.yaml` + `agentcore deploy` run from `agent/`.

`.planning/` contains phase-by-phase deployment notes (OIDC, IAM access keys, SAM parameter overrides) — check there for why specific infra/CI choices were made before changing `infra/template.yaml` or `.github/workflows/`.

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed execution, observability, and audit logging. If unavailable, use the AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with `retrieve_skill` and prefer its guidance over general knowledge.
- When uncertain about specific AWS details (API parameters, permissions, limits, error codes), verify against documentation rather than guessing. State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework principles.
- Do not use em dashes in AWS resource names or descriptions. Use hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret, credential, API key, token, or password task. MUST NOT call `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST NOT hit the Secrets Manager Agent daemon directly. MUST use `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with `asm-exec` so the secret resolves at runtime without entering context.
