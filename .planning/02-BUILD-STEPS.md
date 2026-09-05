# 02 — Build steps (ordered)

## Phase 0 — Bootstrap (Console, human)

- [ ] Confirm AWS account + AgentCore region  
- [ ] Enable Bedrock model access (Haiku / Nova Lite)  
- [ ] Create GitHub OIDC → IAM deploy role  
- [ ] AWS Budgets alert $25 / $50  
- [ ] Create/connect GitHub remote  

## Phase 1 — Knowledge corpus

- [x] Write `docs/kb/admission/` sample docs  
- [x] Write `docs/kb/exams/` sample docs  
- [x] Write `docs/kb/regulations/` sample docs  
- [x] Write `docs/kb/fees/` sample docs  
- [x] Align content with golden prompts  

## Phase 2 — Tools

- [x] `get_admission_deadline` Lambda  
- [x] `get_exam_schedule` Lambda  
- [x] `create_ticket` Lambda  
- [x] Unit tests for each tool  

## Phase 3 — Agent + RAG

- [x] Agent entrypoint (Python AgentCore app)  
- [x] Local KB retrieval + tools in `campus_logic`  
- [ ] Register tools via AgentCore Gateway (AWS account step)  
- [x] System prompt: answer only from KB; cite sources  
- [x] AgentCore direct code (ZIP) config — no Docker  

## Phase 4 — Public API + UI

- [x] Invoke Lambda + API Gateway `POST /chat` (SAM)  
- [x] Vite CampusAssist UI (header, chips, chat, citations, tool badge)  
- [x] `sessionId` in sessionStorage  
- [x] Local UI smoke against mock API (`scripts/local_api.py`)  

## Phase 5 — Infra + CI/CD

- [x] Infra templates (S3, CF, API, Lambdas, IAM)  
- [x] `.github/workflows/deploy.yml`  
- [x] `.github/workflows/teardown.yml` + `scripts/teardown.sh`  
- [x] README with golden prompts + deploy vars  

## Phase 6 — First deploy + harden

- [ ] Push `main` → Actions green  
- [ ] Run full test matrix ([03-TEST-PLAN.md](03-TEST-PLAN.md))  
- [ ] Rehearse demo script ([05-DEMO-SCRIPT.md](05-DEMO-SCRIPT.md))  
- [ ] Record 30s backup video  
