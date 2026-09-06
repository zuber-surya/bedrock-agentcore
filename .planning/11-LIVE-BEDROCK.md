# 11 — Enable live Bedrock (required for no-mock)

## Marketplace vs Amazon models

| Path | Models | Marketplace ProductId | IAM needed for first enable |
|------|--------|----------------------|-----------------------------|
| **Amazon (no Marketplace)** | Nova Lite/Pro/…, DeepSeek, Mistral, Meta, Qwen, OpenAI | **None** — cannot scope `aws-marketplace:*` to these | Payment + account authorization; normal `bedrock:InvokeModel` / `Converse` |
| **AWS Marketplace (3P)** | Anthropic Claude, Cohere, Stability, … | Yes | `aws-marketplace:Subscribe`, `Unsubscribe`, `ViewSubscriptions` **once** to auto-subscribe, then Bedrock invoke only |

CampusAssist demo model is **Amazon Nova Lite** (`us.amazon.nova-lite-v1:0`). Marketplace IAM does **not** authorize Nova. It is still attached so Anthropic/other 3P models can auto-subscribe later if needed.

### Marketplace policy (repo + attached identities)

- Policy file: [`infra/bedrock-marketplace-access.json`](../infra/bedrock-marketplace-access.json)
- Inline policy name: `BedrockMarketplaceAccess`
- Attached to:
  - IAM user **`campusassist-gha`** (CI / deploy)
  - Lambda role **`campusassist-InvokeFunctionRole-Nw6owNcipgBz`**
- Also declared on the SAM Invoke function in [`infra/template.yaml`](../infra/template.yaml) so redeploys keep Marketplace actions

## Current blocker (account-level, not IAM)

Account `771495376060` / region `us-east-1`:

```
get-foundation-model-availability (amazon.nova-lite-v1:0)
  agreementAvailability: AVAILABLE
  entitlementAvailability: AVAILABLE
  regionAvailability: AVAILABLE
  authorizationStatus: NOT_AUTHORIZED   ← blocks runtime

converse(us.amazon.nova-lite-v1:0) → ValidationException: Operation not allowed

Nova Lite service quotas (ACCOUNT applied): RPM/TPM = 0
  (cross-region TPM default advertised elsewhere as ~8M; applied Value is 0)

freetier get-account-plan-state → Missing data for account
```

Marketplace policy is in place. This is **not** fixed by more Marketplace IAM for Nova. Typical causes for new accounts: Bedrock runtime verification hold, payment not fully verified for Bedrock, or zero applied model quotas until AWS authorizes the account.

### Checks already done

1. **Payment / spend:** Cost Explorer shows tiny spend; monthly budget `$5` exists; caller is root via profile `campusassist`.
2. **Plan:** `aws freetier get-account-plan-state` returns missing data (new AWS experience gap). Confirm Free/Paid + Bedrock eligibility in [AWS Settings](https://settings.aws.com/) / Billing.
3. **Quota request:** `L-7C42E72A` Cross-region model inference tokens per minute for Amazon Nova Lite → desired `8000001`, request id `3c985079fb304787bb723ff21c33f1a9FmPKouYc`, status **`CASE_OPENED`**, Support **CaseId `178867579400221`**. Applied quota still `0` until approved. Reply in Support Center if AWS asks for more info.
4. **Anthropic FTU form:** `get-use-case-for-model-access` → form not filled. **Not required for Nova.** Fill only if you later switch to Claude (`PutUseCaseForModelAccess` + Marketplace subscribe).

### What you must do in console (cannot finish via CLI alone while NOT_AUTHORIZED)

1. Open https://console.aws.amazon.com/bedrock/home?region=us-east-1  
2. Confirm payment at https://settings.aws.com/ (Billing / payment method).  
3. Open **Nova Lite** in model catalog / playground and try one prompt.  
4. If console says account verification in progress / Operation not allowed: open **Account and billing** support case (Basic support) asking to lift Bedrock runtime hold; cite `authorizationStatus: NOT_AUTHORIZED` and applied Nova quotas = 0.  
5. Re-check:

```powershell
aws bedrock get-foundation-model-availability --model-id amazon.nova-lite-v1:0 --region us-east-1 --profile campusassist
```

Expect `authorizationStatus: AUTHORIZED`.

## After access is granted

Live env is already:

- `MOCK_MODE=false`
- `USE_BEDROCK=true`
- `BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0`

Smoke:

```powershell
$body = '{"message":"What is the minimum attendance for semester exams?","sessionId":"live-1"}'
Invoke-RestMethod -Uri "https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat" -Method POST -Body $body -ContentType "application/json"
```

Expect `"mode": "live-bedrock"` and **no** `bedrockError`.

UI: https://campusassist-ui-771495376060.s3.us-east-1.amazonaws.com/index.html

## Optional later: Claude

1. Keep Marketplace policy (already attached).  
2. Submit Anthropic FTU once (console or `put-use-case-for-model-access`) with use-case + URL (GitHub repo OK).  
3. First Claude invoke auto-subscribes via Marketplace.  
4. Change `BEDROCK_MODEL_ID` only if intentionally leaving Nova.

## Optional later: AgentCore Runtime

Once Bedrock works, deploy `agent/` with AgentCore CLI and set `AGENT_RUNTIME_ARN` so Invoke Lambda calls Runtime instead of in-Lambda campus_logic.
