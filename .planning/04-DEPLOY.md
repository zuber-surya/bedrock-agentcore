# 04 — Deploy: GitHub → AWS

## One-time Console

1. Bedrock model access  
2. IAM role trusted by GitHub OIDC (`token.actions.githubusercontent.com`)  
3. Permissions: S3, Lambda, API Gateway, CloudFront, AgentCore, Bedrock, IAM pass-role as needed  
4. Store `AWS_ROLE_ARN` (and region) as GitHub Actions variables/secrets  

## Every push to `main`

Workflow `deploy.yml`:

1. Checkout  
2. Build `ui/`  
3. Sync `docs/kb/` → S3; sync Managed KB  
4. Deploy Lambdas + API Gateway  
5. AgentCore Runtime **direct code ZIP** deploy (no Docker)  
6. Upload UI → S3; CloudFront invalidation  
7. Echo public URL  

## Tear down

- Manual `workflow_dispatch` on teardown workflow, or `scripts/teardown.sh`  
- Delete Runtime agent, KB, API, CloudFront, demo buckets  

## Agent packaging (no manual zip, no Docker)

**Direct code deploy** = AgentCore’s ZIP-based deploy mode (alternative to containers).

| You do | Tool does |
|---|---|
| Write Python agent in `agent/` | — |
| Run `agentcore` CLI (or GitHub Actions runs it) | Packages code + deps into a ZIP and deploys to AgentCore Runtime |
| — | You do **not** manually zip folders or build Docker images |

**Excluded:** Docker, ECR, CodeBuild-for-containers.  
**Not excluded:** automated ZIP packaging by the CLI/pipeline.
