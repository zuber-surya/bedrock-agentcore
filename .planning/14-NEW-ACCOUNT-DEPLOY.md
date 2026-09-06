# 14 — New-account deployment plan (IAM user `zuber` / `390403887579`)

## Why move
Personal CampusAssist account `771495376060` is blocked for Bedrock Converse and AgentCore quotas.  
Crest SSO was a temporary test path. **Target account for the new deploy is now `390403887579` (IAM user `zuber`).**

## Phase 0 — Confirm Bedrock (verified)
- [x] Identity: `arn:aws:iam::390403887579:user/zuber`
- [x] Nova Lite `authorizationStatus: AUTHORIZED`
- [x] Converse works
- [x] `python -m agent.main "…attendance…"` → `mode=live-bedrock`
- [ ] Local API + UI smoke
- [ ] AgentCore `list-agent-runtimes` (empty today — new runtime OK to create)

## Phase 1 — Permissions
Confirm user `zuber` (or a deploy role it can assume) can create:
- CloudFormation / SAM, Lambda, API Gateway, S3
- IAM roles for Lambda / KB / AgentCore
- `bedrock:*`, `bedrock-agentcore:*`

## Phase 2 — Fresh resource names
| Resource | Suggested name |
|----------|----------------|
| Stack | `campusassist` or `campusassist-zuber` |
| Docs bucket | `campusassist-kb-zuber-390403887579` |
| UI bucket | `campusassist-ui-390403887579` |
| Managed KB | `campusassist-kb` |
| AgentCore runtime | `campusassistagent` |

Do not reuse ARNs from `771495376060`.

## Phase 3 — Deploy order
1. SAM stack → sync KB → build/sync UI  
2. Managed KB + ingest  
3. AgentCore Runtime from `agent/`  
4. Set `AGENT_RUNTIME_ARN` on invoke Lambda  
5. Smoke golden prompts  

## Credentials
Store only in gitignored `.env` or IAM profile. Keys pasted in chat should be **rotated** after the demo.

Say **deploy to zuber** to start Phase 1–3.
