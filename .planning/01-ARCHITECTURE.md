# 01 — Architecture

## Services (8 core)

1. Amazon Bedrock (model)  
2. AgentCore Runtime  
3. AgentCore Gateway  
4. Managed Knowledge Base  
5. S3 (docs + UI)  
6. Lambda (tools + invoke proxy)  
7. API Gateway  
8. CloudFront  

Supporting: IAM, CloudWatch. Optional later: Bedrock Guardrails.

## Request path

```
Browser
  → CloudFront → S3 (CampusAssist UI)
  → API Gateway POST /chat
  → Invoke Lambda
  → AgentCore Runtime
       → Bedrock model
       → Managed Knowledge Base ← S3 docs
       → Gateway → Tool Lambdas
```

## Repo layout (to implement)

```
docs/kb/           Sample college Markdown
agent/             Python agent (ZIP → AgentCore)
lambda/tools/      deadline, schedule, ticket
lambda/invoke/     API → Runtime proxy
infra/             SAM/CDK or CLI templates
ui/                Vite CampusAssist
.github/workflows/ deploy.yml + teardown
scripts/           teardown helpers
README.md
```
