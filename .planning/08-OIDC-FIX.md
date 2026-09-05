# Fix: GitHub Actions OIDC `AssumeRoleWithWebIdentity` denied

Error: `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`

Role `campusassist-github` shows **RoleLastUsed empty** — it has never been assumed successfully.

---

## Why it fails

AWS rejects the GitHub OIDC token when **any** of these are wrong:

1. OIDC provider missing / bad client ID / stale provider  
2. Trust policy `sub` / `aud` does not match the token  
3. `sts:TagSession` mishandled in the same conditioned statement  
4. Account SCP / org deny on federation (less common on personal accounts)

Your workflow already has `permissions: id-token: write` (required) — that part is fine.

---

## Fix A — Recreate OIDC (recommended)

Run in PowerShell (AWS CLI logged in as admin/root):

```powershell
# 1) Detach inline policy and delete role
aws iam delete-role-policy --role-name campusassist-github --policy-name CampusAssistDeploy
aws iam delete-role --role-name campusassist-github

# 2) Delete OIDC provider
aws iam delete-open-id-connect-provider `
  --open-id-connect-provider-arn arn:aws:iam::771495376060:oidc-provider/token.actions.githubusercontent.com

# 3) Recreate OIDC provider (GitHub)
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com `
  --thumbprint-list ffffffffffffffffffffffffffffffffffffffff

# 4) Recreate role with trust from repo file
aws iam create-role `
  --role-name campusassist-github `
  --assume-role-policy-document file://infra/github-oidc-trust.json

aws iam put-role-policy `
  --role-name campusassist-github `
  --policy-name CampusAssistDeploy `
  --policy-document file://infra/github-oidc-policy.json

# 5) Confirm ARN (must match GitHub var)
aws iam get-role --role-name campusassist-github --query Role.Arn --output text
```

GitHub → Settings → Variables → Actions:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::771495376060:role/campusassist-github` |

Then: Actions → **Deploy CampusAssist** → Run workflow.

**Pass if:** step **Configure AWS credentials (OIDC)** is green.

---

## Fix B — Bypass OIDC (fastest for demo)

If A still fails (account quirk), use IAM user keys for CI only:

1. IAM → Create user `campusassist-gha` → Access key  
2. Attach same deploy permissions as `CampusAssistDeploy`  
3. GitHub → Settings → **Secrets** (not variables):

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | from IAM |
| `AWS_SECRET_ACCESS_KEY` | from IAM |

4. Change workflow step to:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: ${{ env.AWS_REGION }}
```

Remove the OIDC `role-to-assume` block for that step.

---

## Trust policy that should work (Fix A)

Already in [`infra/github-oidc-trust.json`](../infra/github-oidc-trust.json):

- Statement 1: `sts:AssumeRoleWithWebIdentity` + `aud` + `sub` = `repo:zuber-surya/bedrock-agentcore:*`  
- Statement 2: `sts:TagSession` (no condition) — needed by `configure-aws-credentials`

---

## Console checklist

1. IAM → Identity providers → `token.actions.githubusercontent.com` exists  
2. Audience / client ID includes `sts.amazonaws.com`  
3. Role trust shows Federated principal = that provider  
4. Repo path in `sub` is exactly `repo:zuber-surya/bedrock-agentcore:*` (owner/repo match GitHub)  
5. Workflow has:

```yaml
permissions:
  id-token: write
  contents: read
```

---

## After it works

You can keep using local `sam deploy` or switch fully to Actions. CloudFront is a **separate** blocker (account verification).
