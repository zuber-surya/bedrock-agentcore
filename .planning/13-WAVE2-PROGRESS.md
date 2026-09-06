# 13 — Wave 2 progress

Started: 2026-09-06

## Done

### Managed Knowledge Base
| Field | Value |
|-------|--------|
| Name | `campusassist-kb` |
| ID | `VJVOXAJ68B` |
| ARN | `arn:aws:bedrock:us-east-1:771495376060:knowledge-base/VJVOXAJ68B` |
| Type | `MANAGED` (no OpenSearch) |
| Role | `CampusAssistBedrockKBRole` |
| Data source | `campusassist-kb-s3` / `Y3MVYVNN21` |
| S3 | `campusassist-kb-zubersurya-771495376060` |
| Ingestion | `FXZ9IJWUUP` **COMPLETE** — 7 docs indexed |

Retrieve verified: “minimum attendance…” → exam-rules.md / attendance-conduct.md (**75%**).

### Repo prep
- `agent/agentcore.yaml` → `USE_BEDROCK=true`, `BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0`
- IAM + JSON helpers under `infra/kb-*.json`, `infra/agentcore-*.json`

## Blocked

### Bedrock model invoke (chat LLM)
- Nova Lite + Titan Embed: `authorizationStatus: NOT_AUTHORIZED`
- Converse: `Operation not allowed`
- Support case: `178867579400221` (`CASE_OPENED`)
- Chat API returns `mode=error` until this clears

### AgentCore Runtime
- IAM role ready: `CampusAssistAgentCoreRuntimeRole`
- Code zip uploaded: `s3://campusassist-kb-zubersurya-771495376060/agentcore/campusassist-agent.zip`
- `create-agent-runtime` failed: **`ServiceQuotaExceededException: maxAgents limit exceeded`** for account `771495376060`
- Same class of new-account restriction as Bedrock invoke / Memory Access Denied
- Intended runtime name: `campusassistagent` (letters only)

## Tools
- Keep **in-process** tool calls in `campus_logic` (Gateway deferred until AgentCore quota allows)

## Next
1. Support: ask to raise **Bedrock AgentCore maxAgents** + clear Nova `AUTHORIZED` (case `178867579400221`)
2. Re-run create-agent-runtime → set `AGENT_RUNTIME_ARN` on `campusassist-invoke`
3. Smoke golden prompts → `live-bedrock` / AgentCore
