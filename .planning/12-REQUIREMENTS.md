# 12 — Requirements, Tech Stack & AWS Services (as-built)

Status snapshot: 2026-09-06 (rewritten — supersedes the earlier version of this doc, which described Wave 1 on account `771495376060` with Nova Lite and `MOCK_MODE`; none of that reflects the current deployment). Reflects what is actually deployed and verified live on account `390403887579` (IAM user `zuber`), not just what was planned in [00-OVERVIEW.md](00-OVERVIEW.md) / [01-ARCHITECTURE.md](01-ARCHITECTURE.md).

---

## 1. Requirements

### Functional

| ID | Requirement |
|---|---|
| F1 | Chat endpoint answers college FAQs on admission, exams, academic regulations, and fees. |
| F2 | Off-topic questions are politely refused, not hallucinated. |
| F3 | Structured queries (admission deadline, exam schedule) are answered by deterministic tools, not free-text generation. |
| F4 | Users can raise a support ticket ("fee clarification") and receive a ticket ID. |
| F5 | Answers backed by knowledge-base content cite the source document, on its own line, separate from the answer text. |
| F6 | Every response returns a consistent JSON contract: `{ reply, citations, toolsUsed, sessionId, mode }`. |
| F7 | A browser-based chat UI is reachable over a public URL without running anything locally. |
| F8 | The chat UI renders the reply's markdown (bold, bullet lists, headings, tables) instead of showing raw markdown syntax. |

### Non-functional / constraints (locked decisions, see [00-OVERVIEW.md](00-OVERVIEW.md))

| ID | Constraint |
|---|---|
| N1 | No Docker, no ECR — agent/tooling deployed as plain Lambda ZIP / AgentCore direct-code deploy. |
| N2 | No OpenSearch Serverless — RAG must not depend on a self-managed vector store. |
| N3 | No EC2. |
| N4 | Infra as code (SAM), deployed via GitHub Actions on push to `main` — currently only wired to the old, abandoned account (see §6). |
| N5 | Demo-grade cost target: ~$5–25 for the build+demo window, budget alerts at $25/$50. |
| N6 | Region: `us-east-1`. |
| N7 | Bedrock is mandatory — there is no mock mode. If both the primary and fallback model calls fail, the raw exception becomes the reply rather than a canned/hardcoded answer. |

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| UI | Vite + vanilla JS/HTML/CSS, single page (`ui/`), dependency-free markdown renderer (bold/bullets/headings/tables) for bot replies |
| API | Amazon API Gateway (HTTP API), `POST /chat` |
| Compute | AWS Lambda, Python 3.12 (`lambda/invoke`, `lambda/tools`) + Bedrock AgentCore Runtime (`agent/`) |
| Model | Amazon Bedrock Converse API — primary `us.anthropic.claude-haiku-4-5-20251001-v1:0`, fallback `us.amazon.nova-lite-v1:0` |
| Knowledge base | Markdown files under `docs/kb/`, section-based keyword match at request time (`_search_kb`/`_kb_sections` in `campus_logic.py`) — a real Bedrock Managed Knowledge Base (`campusassist-kb`) exists and is ingested but is not called by any code path (see §4 gap notes) |
| IaC | AWS SAM (`infra/template.yaml`) |
| CI/CD | GitHub Actions (`.github/workflows/deploy.yml`, `teardown.yml`) |
| Storage | Amazon S3 (KB docs bucket + UI static-site bucket) |
| Testing | Python `unittest` (`lambda/tests/test_tools.py`) |
| Agent runtime | Bedrock AgentCore Runtime — deployed and live (`agent/`, `agent/agentcore.yaml`), invoke Lambda routes to it via `AGENT_RUNTIME_ARN` |

---

## 3. AWS services in use, with reference docs

| Service | Used for | Status | AWS docs |
|---|---|---|---|
| **IAM** | User `zuber`; Lambda/AgentCore/KB execution roles; `aws-marketplace:Subscribe/Unsubscribe/ViewSubscriptions` grant (Nova Lite is Marketplace-listed) | Live | https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html |
| **AWS CloudFormation** (via **AWS SAM**) | Deploys the whole `campusassist` stack from `infra/template.yaml` | Live | https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html · https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html |
| **Amazon S3** | `campusassist-kb-zuber-390403887579` (KB docs, synced from `docs/kb/`); `campusassist-ui-390403887579` (static website hosting for the UI) | Live | https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html |
| **AWS Lambda** | `campusassist-invoke` (the `/chat` handler, routes to AgentCore Runtime); 3 standalone tool functions (deployed, not wired to any caller) | Live | https://docs.aws.amazon.com/lambda/latest/dg/welcome.html |
| **Amazon API Gateway** (HTTP API) | `POST /chat` + `OPTIONS /chat` (CORS) → invoke Lambda, stage `prod` | Live | https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api.html |
| **Amazon Bedrock — Converse API** | LLM call in `bedrock_generate()`; primary `us.anthropic.claude-haiku-4-5-20251001-v1:0`, fallback `us.amazon.nova-lite-v1:0` on failure | Live (`mode: live-bedrock`) | https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html |
| **Bedrock AgentCore Runtime** | `campusassistagent-4AErABEsnY`; invoke Lambda calls it via `AGENT_RUNTIME_ARN` and `invoke_agent_runtime` | Live | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html |
| **Bedrock Knowledge Bases** | `campusassist-kb`, 7 docs ingested from the docs S3 bucket, manually verified via console Retrieve | **Provisioned but unused** — no code calls Retrieve/RetrieveAndGenerate; the app still keyword-searches bundled markdown locally | https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html |
| **Amazon CloudWatch** | Lambda/API Gateway logs; explicit structured `_mlog(...)` lines in `campus_logic.py` designed for CloudWatch | Live (implicit) | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html |
| **Amazon CloudFront** | Was planned for HTTPS UI hosting | **Not used** — blocked by account verification on the old account; this account's UI runs off plain S3 website hosting (HTTP only) instead | https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html |
| **AWS Marketplace** | Model subscription Nova Lite requires before Bedrock will invoke it (fallback path) | Live (permission, not a standalone resource) | https://docs.aws.amazon.com/marketplace/latest/buyerguide/buyer-getting-started.html |

Not AWS: **GitHub Actions** drives `sam deploy`, but its secrets still point at the old, abandoned account (`771495376060`) — see §6.

---

## 4. Known gaps against the target architecture

- **Managed Knowledge Base is provisioned but disconnected.** `campusassist-kb` exists, is ingested, and was verified once via the console — nothing in `agent/campus_logic.py` / `lambda/invoke/campus_logic.py` calls `bedrock-agent-runtime` Retrieve. RAG grounding today is entirely the local `_search_kb` keyword/section match over bundled markdown.
- **AgentCore Gateway is not used.** The three tool Lambdas (`AdmissionDeadlineFunction`, `ExamScheduleFunction`, `CreateTicketFunction`) are deployed but nothing calls them over the network — `gather_context()` calls the same Python functions in-process instead.
- **Triple file duplication, kept in sync by hand** (SAM's `CodeUri` for `InvokeFunction` is `lambda/invoke/`, so anything the Lambda needs at runtime must physically live there — no build step copies it in):
  - `agent/campus_logic.py` == `lambda/invoke/campus_logic.py`
  - `lambda/tools/handlers.py` == `lambda/invoke/handlers.py`
  - `docs/kb/**/*.md` == `lambda/invoke/kb/**/*.md`
- **System prompt references tools that don't exist**: `agent/campus_logic.py`'s `SYSTEM` constant mentions `checkStudentRecord` and `raiseGrievance`, neither of which is implemented (the real tools are `create_ticket`, `get_admission_deadline`, `get_exam_schedule`). Flagged, not yet fixed.
- **CloudFront was never retried on this account** — the account-verification block was hit on `771495376060`; nobody has attempted CloudFront on `390403887579` yet. The UI is served over plain HTTP via S3 website hosting.

---

## 5. Live endpoints (current — account `390403887579`)

| What | Value |
|---|---|
| Chat API | `https://hrw28diu26.execute-api.us-east-1.amazonaws.com/prod/chat` |
| UI (S3 static site, HTTP only) | `http://campusassist-ui-390403887579.s3-website-us-east-1.amazonaws.com` |
| Docs bucket | `campusassist-kb-zuber-390403887579` |
| Managed KB | `campusassist-kb` |
| AgentCore Runtime | `campusassistagent-4AErABEsnY` |
| Stack | `campusassist` (CloudFormation, `us-east-1`) |

Verified live (2026-09-06): `POST /chat` with "what is the tution fees for B.Tech" returns `mode: "live-bedrock"`, the correct fee table figures (₹75,000 tuition/semester, etc.), and a `Source: fees/fee-policy.md` line per the system prompt's citation format.

## 6. Open items

- [ ] **GitHub Actions still deploys to the old account** (`771495376060`, secrets never rotated after the move to `zuber`). A push to `main` does not affect the live endpoints above — every deploy so far has been manual.
- [ ] Wire `_search_kb` to actually call the provisioned Managed Knowledge Base instead of local keyword search.
- [ ] Register the three tool Lambdas as AgentCore Gateway tools instead of in-process calls.
- [ ] Fix the `checkStudentRecord`/`raiseGrievance` mismatch in the system prompt.
- [ ] Decide whether to pursue CloudFront + HTTPS on the new account, or accept HTTP-only S3 hosting for the demo.
