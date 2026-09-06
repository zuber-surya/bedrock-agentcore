# CampusAssist — Help request / issue brief

**Date:** 2026-09-05  
**AWS Account ID:** `771495376060`  
**Region:** `us-east-1`  
**GitHub repo:** https://github.com/zuber-surya/bedrock-agentcore  
**Project:** CampusAssist — college FAQ chatbot demo (Bedrock + RAG + Agents + AgentCore)

---

## What we are trying to do

Build and host a **live demo** for college students and professionals:

1. **Chat UI (CampusAssist)** served over **HTTPS** on a public URL  
2. Backend on AWS:
   - API Gateway `POST /chat`
   - Lambda (invoke + tool functions)
   - S3 for knowledge-base docs
   - Later: Bedrock + AgentCore Runtime + Managed Knowledge Base (no OpenSearch Serverless)
3. Deploy via **GitHub Actions** (SAM) on push to `main`

**Current working pieces:**

| Piece | Status |
|---|---|
| Code + GitHub repo | Done |
| Chat API (mock mode) | **Live** — `https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat` |
| CloudFormation stack `campusassist` | Deployed (API + Lambdas + docs S3) |
| GitHub Actions deploy | **Working** via IAM user access keys (`campusassist-gha`) |
| Local UI → live API | Works with `VITE_API_URL` |

**Architecture (target):**

```
Browser → CloudFront → S3 (static UI)
       → API Gateway /chat → Lambda → (mock today / AgentCore later)
                                      → S3 KB docs / Managed KB
```

We intentionally **do not** use OpenSearch Serverless or Docker for this demo.

---

## Issue 1 (BLOCKING) — CloudFront account verification

### Goal
Host the CampusAssist UI on **CloudFront + S3** so the audience opens one public HTTPS URL (no local Vite).

### What happens
Creating a CloudFront distribution fails with **403 Access Denied**:

> Your account must be verified before you can add new CloudFront resources.  
> To verify your account, please contact AWS Support and include this error message.  
> (Service: CloudFront, Status Code: 403)

### Evidence
- `aws cloudfront list-distributions` succeeds (empty list / no create)
- CloudFormation resource `AWS::CloudFront::Distribution` → `CREATE_FAILED` with the message above
- Stack update rolled back; API stack remains healthy (`UPDATE_ROLLBACK_COMPLETE` after failed CF add)

### Example Request IDs (from failed creates)
- `1959f017-3241-4fdd-abcb-c310b60c5522`
- `3483aa47-83b5-488d-8df4-718140f6f8df`

### What we need from AWS Support
Please **verify this account for CloudFront** so we can create distributions in `us-east-1` (and generally enable CloudFront for the account).

### Workaround today
Run UI locally pointed at the live API:

```powershell
cd ui
$env:VITE_API_URL="https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat"
npm run dev
```

---

## Issue 2 (RESOLVED) — GitHub Actions OIDC

### Original error
```
Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity
```
Role: `arn:aws:iam::771495376060:role/campusassist-github`  
OIDC provider: `token.actions.githubusercontent.com`  
Repo trust: `repo:zuber-surya/bedrock-agentcore:*`

Role showed **RoleLastUsed empty** (never successfully assumed).

### Resolution applied
Switched CI to **IAM user access keys** (Fix B):

- IAM user: `campusassist-gha`
- GitHub Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- Workflows no longer use OIDC `role-to-assume`
- Latest deploy run: **success**  
  https://github.com/zuber-surya/bedrock-agentcore/actions/runs/33978657871

OIDC can be revisited later; not blocking the demo.

---

## What is still pending (after CloudFront is fixed)

1. Add CloudFront + UI bucket back to `infra/template.yaml` and redeploy  
2. Publish `ui/dist` to S3 and invalidate CloudFront  
3. Put public UI URL on presentation slides  
4. Wave 2: AgentCore Runtime + Managed Knowledge Base + `MOCK_MODE=false`

---

## Ask (one sentence)

**Please verify AWS account `771495376060` for CloudFront so we can create a distribution in `us-east-1` for our CampusAssist demo UI.**

---

## Contacts / links

- Repo: https://github.com/zuber-surya/bedrock-agentcore  
- Live API: https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat  
- Stack name: `campusassist`  
- Docs bucket: `campusassist-kb-zubersurya-771495376060`
