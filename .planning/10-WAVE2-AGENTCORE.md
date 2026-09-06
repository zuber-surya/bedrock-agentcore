# 10 — Wave 2 checklist: Agents + AgentCore

UI is live on S3. API still runs **mock** (`MOCK_MODE=true`, no AgentCore ARN).  
Use this list to move to real **Bedrock + AgentCore + tools + Managed KB**.

**UI:** https://campusassist-ui-771495376060.s3.us-east-1.amazonaws.com/index.html  
**API:** https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat  

---

## A. Confirm UI → API first (5 min)

Before AgentCore, prove the hosted UI talks to AWS:

- [ ] Open S3 UI URL in browser  
- [ ] DevTools → Network: chat requests go to API Gateway `/prod/chat` (not localhost)  
- [ ] If UI was built with wrong `VITE_API_URL`, rebuild:  
  `cd ui && set VITE_API_URL=https://3wfx35hyp2.execute-api.us-east-1.amazonaws.com/prod/chat && npm run build`  
  then sync `dist/` to `campusassist-ui-771495376060`  
- [ ] Run all 5 golden prompts; expect citations / tool badges (mock path is OK)

---

## B. Bedrock model access (Console)

- [ ] Region `us-east-1` → Bedrock → Model access  
- [ ] Enable **Amazon Nova Lite** and/or **Claude Haiku**  
- [ ] Test in Bedrock playground that the model responds  

---

## C. Managed Knowledge Base (RAG) — no OpenSearch Serverless

- [ ] AgentCore / Bedrock → create **Managed Knowledge Base**  
- [ ] Data source: `s3://campusassist-kb-zubersurya-771495376060/kb/`  
- [ ] Sync / ingest docs  
- [ ] Test retrieve in console with: “minimum attendance for semester exams”  
- [ ] Note KB ID / ARN for the agent  

---

## D. Deploy agent to AgentCore Runtime (direct code ZIP)

From repo `agent/` (no Docker):

- [ ] Install AgentCore CLI  
- [ ] Set env: `USE_BEDROCK=true`, `BEDROCK_MODEL_ID=<your-model-id>`  
- [ ] Wire KB id into agent config / code if required by CLI  
- [ ] `agentcore deploy` (or equivalent) using [`agent/agentcore.yaml`](../agent/agentcore.yaml)  
- [ ] Copy **Agent Runtime ARN**  

---

## E. Tools via AgentCore Gateway

Already deployed Lambdas:

- `campusassist-admission-deadline`  
- `campusassist-exam-schedule`  
- `campusassist-create-ticket`  

- [ ] Register each as Gateway tools for the agent  
- [ ] Confirm agent can call them (admission deadline → `2026-06-30`)  

---

## F. Point Invoke Lambda at AgentCore (leave mock behind)

- [ ] Set Lambda env `AGENT_RUNTIME_ARN` = Runtime ARN  
- [ ] Set `MOCK_MODE=false`  
- [ ] Or set GitHub vars `AGENT_RUNTIME_ARN` + `MOCK_MODE=false` and re-run **Deploy CampusAssist**  
- [ ] Smoke API:  
  - Attendance → answer + citations from KB  
  - B.Tech last date → tool badge + deadline  
  - Fee ticket → `TKT-…`  
  - “poem about Mars” → refuse  

---

## G. What “done” looks like for the talk

| Check | Pass |
|---|---|
| Hosted UI URL works | S3 (or CloudFront later) |
| Answer cites handbook | Managed KB / RAG |
| Deadline uses tool | Agent + Gateway + Lambda |
| Hosting story | AgentCore Runtime Active in console |
| Not mock | `MOCK_MODE=false` |

---

## Order (do not skip)

1. UI → API wired (A)  
2. Bedrock model access (B)  
3. Managed KB sync (C)  
4. AgentCore deploy (D)  
5. Gateway tools (E)  
6. Flip `MOCK_MODE=false` (F)  
7. Full golden-prompt rehearsal (G)  

Say **start Wave 2** when you want help with steps B–F in order.
