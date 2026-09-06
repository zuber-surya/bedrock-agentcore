# 12 — Requirements, Tech Stack & AWS Services (as-built)

Status snapshot: 2026-09-06. Reflects what is actually deployed and verified live, not just what was planned in [00-OVERVIEW.md](00-OVERVIEW.md) / [01-ARCHITECTURE.md](01-ARCHITECTURE.md). Where the two differ, this doc calls it out explicitly.

---

## 1. Requirements

### Functional

| ID | Requirement |
|---|---|
| F1 | Chat endpoint answers college FAQs on admission, exams, academic regulations, and fees. |
| F2 | Off-topic questions are politely refused, not hallucinated. |
| F3 | Structured queries (admission deadline, exam schedule) are answered by deterministic tools, not free-text generation. |
| F4 | Users can raise a support ticket ("fee clarification") and receive a ticket ID. |
| F5 | Answers backed by knowledge-base content include a source citation. |
| F6 | Every response returns a consistent JSON contract: `{ reply, citations, toolsUsed, sessionId }`. |
| F7 | A browser-based chat UI is reachable over a public URL without running anything locally. |

### Non-functional / constraints (locked decisions, see [00-OVERVIEW.md](00-OVERVIEW.md))

| ID | Constraint |
|---|---|
| N1 | No Docker, no ECR — agent/tooling deployed as plain Lambda ZIP / AgentCore direct-code deploy. |
| N2 | No OpenSearch Serverless — RAG must not depend on a self-managed vector store. |
| N3 | No EC2. |
| N4 | Infra as code (SAM), deployed via GitHub Actions on push to `main`. |
| N5 | Demo-grade cost target: ~$5–25 for the build+demo window, budget alerts at $25/$50. |
| N6 | Region: `us-east-1` (chosen over `ap-south-1` since AgentCore availability wasn't confirmed there). |

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| UI | Vite + vanilla JS/HTML/CSS, single page (`ui/`) |
| API | Amazon API Gateway (HTTP API), `POST /chat` |
| Compute | AWS Lambda, Python 3.12 (`lambda/invoke`, `lambda/tools`) |
| Model | Amazon Bedrock Converse API, model `us.amazon.nova-lite-v1:0` (Nova Lite) |
| Knowledge base | Markdown files under `docs/kb/`, keyword-matched at request time (see §4 gap notes — not yet a Bedrock Managed Knowledge Base) |
| IaC | AWS SAM (`infra/template.yaml`) |
| CI/CD | GitHub Actions (`.github/workflows/deploy.yml`, `teardown.yml`) |
| Storage | Amazon S3 (KB docs bucket + UI static-site bucket) |
| Testing | Python `unittest` (`lambda/tests/test_tools.py`) |
| Agent runtime (planned, not yet live) | Bedrock AgentCore Runtime + Gateway (`agent/`, `agent/agentcore.yaml`) |

---

## 3. AWS services in use — step by step

Each step is what was actually configured/deployed, in the order it happened, with the AWS service(s) it introduced.

1. **IAM** — created IAM user `campusassist-gha` with an access-key pair for GitHub Actions (switched away from an OIDC role after `sts:AssumeRoleWithWebIdentity` kept failing — see [08-OIDC-FIX.md](08-OIDC-FIX.md)). Also created the execution roles SAM auto-generates for each Lambda, and a policy statement granting the invoke Lambda `bedrock:*`, `bedrock-agentcore:*`, and `aws-marketplace:Subscribe/Unsubscribe/ViewSubscriptions` (the last one needed because Nova Lite is a Marketplace-listed model).
2. **AWS CloudFormation (via AWS SAM)** — `infra/template.yaml` defines and deploys every resource below as one stack, `campusassist`.
3. **Amazon S3** — two buckets:
   - `campusassist-kb-zubersurya-771495376060` (`DocsBucket`) — holds the KB markdown docs, synced from `docs/kb/` on every deploy.
   - `campusassist-ui-771495376060` (`UiBucket`) — static website hosting for the built Vite UI (public read, `index.html` as both index and error document). Added specifically as an HTTP fallback because CloudFront is blocked (see step 8).
4. **AWS Lambda** — four functions, all Python 3.12, deployed as plain ZIP (no container/ECR per constraint N1):
   - `campusassist-invoke` — the `/chat` handler; decides mock vs. AgentCore vs. direct Bedrock path (see §4).
   - `campusassist-admission-deadline`, `campusassist-exam-schedule`, `campusassist-create-ticket` — standalone tool functions defined in the stack but not yet wired to anything that calls them over the network (the invoke path currently calls the same Python functions in-process instead of through Gateway — see gap notes).
5. **Amazon API Gateway (HTTP API)** — `POST /chat` and `OPTIONS /chat` (CORS preflight) routed to the invoke Lambda, stage `prod`.
6. **Amazon Bedrock (Converse API)** — invoke Lambda calls `bedrock-runtime.converse()` directly with model `us.amazon.nova-lite-v1:0` when `USE_BEDROCK=true`. Model access request submitted in Bedrock console; **not yet approved** (`ValidationException: Operation not allowed`) — see step 9.
7. **Amazon CloudWatch** — implicit: Lambda + API Gateway logs and metrics (default SAM/Lambda wiring, no custom dashboards/alarms yet).
8. **Amazon CloudFront** — attempted, blocked. Creating a distribution returns `403 Access Denied — Your account must be verified before you can add new CloudFront resources` (see [09-HELP-REQUEST.md](09-HELP-REQUEST.md)). AWS Support case needed; S3 static-site hosting (step 3) is the interim public-URL workaround.
9. **Bedrock model access request** — submitted via console for Nova Lite; account `771495376060` has not completed the use-case form, so live calls fall back to a grounded (tool + KB, no LLM) answer with `mode: live-grounded` instead of `mode: live-bedrock` (see [11-LIVE-BEDROCK.md](11-LIVE-BEDROCK.md)).
10. **GitHub Actions (external to AWS, but drives all of the above)** — on push to `main`: run unit tests → configure AWS credentials (access keys) → `sam deploy` → sync `docs/kb` to S3 → build UI with the live API URL baked in → sync `ui/dist` to the UI bucket → invalidate CloudFront only if a distribution exists.

### Not yet implemented (planned in [01-ARCHITECTURE.md](01-ARCHITECTURE.md), still pending)

- **Bedrock AgentCore Runtime** — `agent/main.py` + `agent/agentcore.yaml` exist and run locally/as a CLI smoke test, but nothing has been deployed to AgentCore Runtime yet; `AGENT_RUNTIME_ARN` is unset, so the invoke Lambda never takes that code path.
- **Bedrock AgentCore Gateway** — the three tool Lambdas are deployed but not registered as Gateway tools; tool calls currently happen via direct Python function calls inside the invoke Lambda.
- **Bedrock Managed Knowledge Base** — "RAG" today is a keyword search over markdown files bundled directly into the Lambda ZIP (`lambda/invoke/kb/`, mirrored from `docs/kb/`), not a real vector-indexed Managed Knowledge Base reading from S3.
- **CloudFront** — blocked on AWS account verification (step 8).

---

## 4. Process followed (chronological)

1. **Scope and lock decisions** — wrote [00-OVERVIEW.md](00-OVERVIEW.md) (goal, audience, excluded services, cost target) and [01-ARCHITECTURE.md](01-ARCHITECTURE.md) (target 8-service architecture, request path, repo layout) before writing code.
2. **Build locally, mock-first** — implemented `lambda/tools/handlers.py` (deadline/schedule/ticket logic), `lambda/invoke/handler.py` (mock chat brain + KB keyword search), the Vite UI, and `scripts/local_api.py` for a no-AWS demo loop. Added `docs/kb/` markdown as the seed knowledge base.
3. **Test** — `lambda/tests/test_tools.py` (unittest) covering tool outputs and mock chat behavior; run in CI before every deploy.
4. **Infra as code** — wrote `infra/template.yaml` (SAM) for the API Gateway + invoke Lambda + tool Lambdas + docs bucket; `infra/samconfig.toml.example` for local `sam deploy` reference.
5. **Wire CI/CD** — `.github/workflows/deploy.yml` (test → deploy → sync KB → build+publish UI) and `teardown.yml`. First attempt used a GitHub OIDC IAM role (`campusassist-github`); it failed to assume (`sts:AssumeRoleWithWebIdentity` not authorized, `RoleLastUsed` empty). Switched to a dedicated IAM user with access-key secrets (Fix B, see [08-OIDC-FIX.md](08-OIDC-FIX.md)) — deploy went green.
6. **Wave 1 — get something live on AWS** — deployed the `campusassist` stack (API Gateway + invoke Lambda + tool Lambdas + docs bucket) with `MOCK_MODE=true`, dropped CloudFront from the template after the account-verification 403 (see [07-AWS-PUSH.md](07-AWS-PUSH.md)), confirmed the `/chat` API live, ran the UI locally against it.
7. **Public UI without CloudFront** — added the `UiBucket` (S3 static website hosting, public read policy) to `infra/template.yaml` and taught `deploy.yml` to publish `ui/dist` to it on every deploy, giving a public HTTP demo URL independent of the CloudFront blocker.
8. **File the CloudFront blocker** — wrote [09-HELP-REQUEST.md](09-HELP-REQUEST.md) as a shareable brief for AWS Support (account ID, exact error, request IDs, what's already working).
9. **Wave 2 — move off mock** — flipped `MOCK_MODE=false`, added `USE_BEDROCK`/`BEDROCK_MODEL_ID` parameters and env vars to the invoke Lambda, added the Marketplace IAM permissions Nova Lite requires, and pointed the live path at `agent/campus_logic.py`-equivalent logic (`run_campus_assist`) instead of the pure mock brain — see [10-WAVE2-AGENTCORE.md](10-WAVE2-AGENTCORE.md) for the full checklist (AgentCore Runtime/Gateway/Managed KB steps in that checklist are still open).
10. **Hit the Bedrock model-access blocker** — live calls to `Converse` return `ValidationException: Operation not allowed` because the account hasn't completed Bedrock's model-access use-case form; documented the fix path in [11-LIVE-BEDROCK.md](11-LIVE-BEDROCK.md). The invoke Lambda degrades gracefully to `mode: live-grounded` (tools + KB, no LLM) instead of failing the request.
11. **Verify current live state** (used to write this doc): `POST /chat` on the live API returns `mode: "live-grounded"` with a `bedrockError` field showing the exact Bedrock rejection — confirming steps 6–10 above are deployed but the model-access step is still blocking full `live-bedrock` mode.

---

## 5. Live endpoints (current)

| What | URL |
|---|---|
| Chat API | `https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat` |
| UI (S3 static site, HTTP only) | `http://campusassist-ui-771495376060.s3-website-us-east-1.amazonaws.com` |
| Docs bucket | `campusassist-kb-zubersurya-771495376060` |
| Stack | `campusassist` (CloudFormation, `us-east-1`) |

## 6. Open items before this matches the original target architecture

- [ ] Get AWS account `771495376060` verified for CloudFront ([09-HELP-REQUEST.md](09-HELP-REQUEST.md)) → move UI to HTTPS.
- [ ] Get Bedrock model access approved for Nova Lite ([11-LIVE-BEDROCK.md](11-LIVE-BEDROCK.md)) → `mode: live-bedrock`.
- [ ] Deploy `agent/` to AgentCore Runtime and set `AGENT_RUNTIME_ARN` ([10-WAVE2-AGENTCORE.md](10-WAVE2-AGENTCORE.md), step D).
- [ ] Register the three tool Lambdas as AgentCore Gateway tools instead of calling them in-process (step E).
- [ ] Replace the bundled-markdown keyword search with a real Bedrock Managed Knowledge Base reading from the docs S3 bucket (step C).
