# 03 — Test plan

## Local

| ID | Test | Pass |
|---|---|---|
| L1 | Tool: admission deadline | Returns fixed demo date + program |
| L2 | Tool: exam schedule | Returns sample mid-sem / end-sem dates |
| L3 | Tool: create ticket | Returns `TKT-xxxxx` |
| L4 | UI loads (`npm run dev`) | Header + 5 chips + composer |
| L5 | UI mock chat | Bubbles render; error state works |

## AWS smoke (after deploy)

| ID | Prompt | Pass |
|---|---|---|
| A1 | Minimum attendance for semester exams? | Answer + citation |
| A2 | Medical leave for missed mid-sem? | Multi-doc grounded answer |
| A3 | Last date for B.Tech admission? | Tool badge + deadline |
| A4 | Documents required for admission? | Citation from admission doc |
| A5 | Raise ticket for fee clarification | Ticket ID from tool |
| A6 | Write a poem about Mars | Refuse / stay on college domain |
| A7 | Open CloudFront URL | HTTPS UI loads |
| A8 | Follow-up in same session | Context retained |

## Pre-talk

- [ ] All A1–A8 on venue Wi‑Fi  
- [ ] AgentCore Runtime = Active in console  
- [ ] Backup recording ready  
