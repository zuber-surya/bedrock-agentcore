# 15 — Deployed on zuber account `390403887579`

Date: 2026-09-06

## Endpoints
| Item | Value |
|------|--------|
| Account | `390403887579` (IAM `zuber`) |
| API | https://hrw28diu26.execute-api.us-east-1.amazonaws.com/prod/chat |
| UI (S3 website) | http://campusassist-ui-390403887579.s3-website-us-east-1.amazonaws.com |
| UI (S3 HTTPS object) | https://campusassist-ui-390403887579.s3.us-east-1.amazonaws.com/index.html |
| Docs bucket | `campusassist-kb-zuber-390403887579` |

## Bedrock / RAG / AgentCore
| Item | Value |
|------|--------|
| Nova | AUTHORIZED (live-bedrock works) |
| Managed KB | `campusassist-kb` / `5OEIVJG5VE` |
| Data source | `GG2C3WMFKH` — ingest COMPLETE (7 docs) |
| AgentCore runtime | `campusassistagent-4AErABEsnY` **READY** |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:390403887579:runtime/campusassistagent-4AErABEsnY` |
| Invoke Lambda env | `AGENT_RUNTIME_ARN` → runtime above (wired) |
| Agent package | arm64 Linux deps vendored in ZIP (`uv pip --python-platform aarch64-manylinux2014`) |
| Runtime version | **2** (deps + `app.run()` entrypoint) |

## Smoke
- Direct `InvokeAgentRuntime` → HTTP **200**, `mode=live-bedrock`
- API `/chat` with ARN set → AgentCore path (not in-Lambda fallback)

## AgentCore fix (2026-09-06)
Root cause: ZIP had source + `requirements.txt` only. Direct code deploy needs **vendored arm64** deps in the archive.  
Also: `main.py` always calls `app.run()` under AgentCore; invoke payload uses flat `{prompt, sessionId}`.

Old account `771495376060` left as-is.
