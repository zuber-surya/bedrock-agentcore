# 00 — Overview

## Goal

Ship **CampusAssist**: a college FAQ chatbot (rules, exams, admission, fees) that demonstrates:

1. **Amazon Bedrock** — foundation model  
2. **RAG** — Managed Knowledge Base (no OpenSearch Serverless)  
3. **Agents + tools** — deadlines, schedule, support ticket  
4. **AgentCore** — Runtime host + Gateway  
5. **Live AWS** — CloudFront HTTPS URL via GitHub Actions  

## Audience

- College students — cited answers to real campus questions  
- Professionals — serverless deploy, CI/CD, observability  

## Locked decisions

| Decision | Choice |
|---|---|
| Product name | CampusAssist |
| RAG store | AgentCore Managed Knowledge Base only |
| OpenSearch Serverless | Excluded |
| Docker / ECR | **Not used.** Agent is deployed with AgentCore **direct code deploy** (CLI builds the ZIP for you) |
| Manual zip by hand | **Not required** — `agentcore` CLI / pipeline packages the agent |
| EC2 | Excluded |
| UI | Vite + vanilla JS, single page |
| Deploy | GitHub Actions (OIDC) |
| Model (cost) | Claude Haiku or Nova Lite |
| Region | `ap-south-1` if AgentCore available, else `us-east-1` |

## Cost target

- Talk week + teardown: **~$5–25**  
- Budget alerts: $25 / $50  
