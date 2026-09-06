# CampusAssist AI agent guide

This repo is a college FAQ chatbot demo built around Amazon Bedrock, managed knowledge base docs, Lambda tools, and an AgentCore runtime. Use this file as the default operational context for coding agents in this workspace.

## Start here

- Project overview: [README.md](README.md)
- Planning docs: [.planning/README.md](.planning/README.md)
- Knowledge base docs: [docs/kb](docs/kb)
- Tool logic: [lambda/tools/handlers.py](lambda/tools/handlers.py)
- API/proxy layer: [lambda/invoke/handler.py](lambda/invoke/handler.py)
- AgentCore runtime entrypoint: [agent/main.py](agent/main.py)
- UI: [ui](ui)

## Architecture and conventions

- The app is intentionally simple and demo-oriented: browser UI -> API Gateway / Lambda -> mock or AgentCore runtime -> Bedrock + Managed KB + tool Lambdas.
- Keep the solution within the existing AWS pattern described in [README.md](README.md): no Docker, no OpenSearch Serverless, no EC2.
- Prefer small, deterministic tool functions and KB-backed answers over custom orchestration complexity.
- Local mock mode is the default when `MOCK_MODE=true` or no `AGENT_RUNTIME_ARN` is set; do not assume AWS is always available.
- The runtime contract for chat responses is JSON with `reply`, `citations`, `toolsUsed`, and `sessionId`.

## Local development

```bash
# Terminal 1 — mock chat API
python scripts/local_api.py

# Terminal 2 — UI
cd ui
npm install
npm run dev
```

Then open http://127.0.0.1:5173. The UI expects the mock chat API and proxies `/chat` requests during local development.

## Tests

```bash
python -m unittest discover -s lambda/tests -v
```

The unit suite in [lambda/tests/test_tools.py](lambda/tests/test_tools.py) covers:

- tool behavior for admission deadlines, exam schedules, and ticket creation
- Lambda wrapper responses
- mock chat flows for valid answers, off-topic filtering, and tool usage

When changing chat logic or tool outputs, update or extend the relevant tests in that file instead of adding unrelated test scaffolding.

## Repo-specific guidance

- Knowledge base content belongs under [docs/kb](docs/kb); update those markdown files before hardcoding new FAQ answers elsewhere.
- Tool handlers in [lambda/tools/handlers.py](lambda/tools/handlers.py) should remain stable and serializable for simple Lambda usage.
- The AgentCore deployment path is via [agent/agentcore.yaml](agent/agentcore.yaml) and `agentcore deploy` from the [agent](agent) directory.
- Deployment details and env variables are documented in [README.md](README.md); follow that source of truth rather than inventing new infrastructure patterns.
- The app is demo-grade; prioritize correctness and repo clarity over broad abstraction or framework churn.

## Do not do

- Do not add Docker-based workflows unless explicitly requested.
- Do not introduce OpenSearch Serverless or custom infra patterns not already described in the repo.
- Do not change the chat response schema without updating the corresponding tests and caller expectations.
- Do not duplicate documentation already captured in the repo; link to existing docs and keep this file concise.

## When making changes

- Prefer the smallest change that matches the existing architecture.
- Validate with the focused unit suite above before claiming the fix is complete.
- Keep behavior deterministic in mock mode so local development and tests stay reproducible.

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed execution, observability, and audit logging. If unavailable, use the AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with `retrieve_skill` and prefer its guidance over general knowledge.
- When uncertain about specific AWS details (API parameters, permissions, limits, error codes), verify against documentation rather than guessing. State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework principles.
- Do not use em dashes in AWS resource names or descriptions. Use hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret, credential, API key, token, or password task. MUST NOT call `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST NOT hit the Secrets Manager Agent daemon directly. MUST use `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with `asm-exec` so the secret resolves at runtime without entering context.
