# CampusAssist

College FAQ chatbot demo: **Amazon Bedrock + RAG + Agents + AgentCore**, hosted on AWS.

Planning docs: [`.planning/`](.planning/README.md)

## What you get

| Piece | Path |
|---|---|
| Knowledge base docs | `docs/kb/` |
| Tool + chat Lambdas | `lambda/` |
| AgentCore agent (ZIP / direct code) | `agent/` |
| CampusAssist UI | `ui/` |
| SAM infra | `infra/template.yaml` |
| CI/CD | `.github/workflows/` |

**No Docker. No OpenSearch Serverless. No EC2.**

## Local demo (no AWS)

```bash
# Terminal 1 — mock chat API
python scripts/local_api.py

# Terminal 2 — UI
cd ui
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies `/chat` to the mock API.

### Unit tests

```bash
python -m unittest discover -s lambda/tests -v
```

## Golden prompts

1. What is the minimum attendance for semester exams?
2. Can I get medical leave for a missed mid-sem?
3. Last date for B.Tech admission this year?
4. What documents are required for admission?
5. Raise a support ticket for fee clarification

## Deploy to AWS (GitHub Actions)

### One-time Console

1. Enable Bedrock model access (Nova Lite / Haiku).
2. Create IAM role for GitHub OIDC; allow CloudFormation, SAM, S3, Lambda, API Gateway, CloudFront, Bedrock/AgentCore as needed.
3. Set AWS Budget alerts ($25 / $50).

### GitHub repository variables

| Variable | Example |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::123:role/campusassist-github` |
| `AWS_REGION` | `us-east-1` or `ap-south-1` |
| `DOCS_BUCKET` | globally unique bucket name |
| `MOCK_MODE` | `true` until AgentCore agent ARN is set |
| `AGENT_RUNTIME_ARN` | (optional) AgentCore runtime ARN |
| `API_URL` | set after first deploy to the API endpoint (or leave; workflow rebuilds UI from stack outputs) |

Push to `main` (or run **Deploy CampusAssist** manually).

AgentCore agent deploy (direct code ZIP, no Docker):

```bash
cd agent
# After AgentCore CLI is installed and configured:
# agentcore deploy  # uses agentcore.yaml
```

Sync KB into Managed Knowledge Base in Console (point at `s3://$DOCS_BUCKET/kb/`) — no OpenSearch Serverless.

### Tear down

Actions → **Teardown CampusAssist**, or:

```bash
./scripts/teardown.sh
```

## Architecture

Browser → CloudFront / S3 UI → API Gateway `/chat` → Invoke Lambda → (mock **or** AgentCore Runtime) → Bedrock + Managed KB + tool Lambdas.
