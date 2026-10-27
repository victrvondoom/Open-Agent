# Unified RECLAIM × PayProof — shared context (read this first)

Target: Open Agent Hackathon 2026, Track 02 "The Agent That Can Explain Why".

## Repositories (both local — do not clone duplicates)
- **Open-Agent / PayProof (primary)**: `C:\Users\Administrator\Downloads\current going on hackathons work\OPEN AGENT HACKATHON\Open-Agent`
  (also reachable via the junction `C:\Users\Administrator\Downloads\CONSUMER\open-agent`). Remote `victrvondoom/Open-Agent`,
  branch `feature/unified-reclaim-openagent`. Stdlib-only Python server `payproof/server.py` (port 8360) + vanilla JS UI in `web/`.
  Domain: sales-commission payment disputes verified across HRIS/CRM/CLM/billing/comp/payroll sources.
  Sponsors: Zetaris (federated SQL REST adapter, `payproof/sources.py`), Meterless (World Model `world_model.py`,
  H-MEM `hmem.py`, Scout `scout.py`), NVIDIA Nemotron (`llm.py`, OpenAI-compatible).
- **RECLAIM (integrate)**: `C:\Users\Administrator\Downloads\CONSUMER` (remote `victrvondoom/RECLAIM`, branch `main`).
  FastAPI backend `backend/app` (LangGraph agents, RAG, knowledge graph, connectors/action fabric), Next.js `frontend/`.
  Consumer disputes across 8 domains (airlines, banking, telecom, e-commerce, housing/RERA, insurance, healthcare, government).

## Verified baseline (2026-10-27, measured)
- `python -m unittest discover -s tests` → 91 tests OK (1 skipped).
- `python -m payproof.bench` → agent 30/30, rules-only 14/30, FP=0 FN=0, unauthorized 0/185, stale blocked 10/10.
- `python run.py --check-integrations` → Meterless WM/H-MEM/Scout ok (in-process), Zetaris + Nemotron NOT configured
  (no credentials exist anywhere on this machine), RECLAIM live at http://127.0.0.1:8001/api/v1.

## Ground rules
- Never fabricate: no invented fields, statuses, citations, benchmark numbers or "LIVE" labels.
- Do not copy competitor code/assets. Ideas and patterns only, with attribution.
- Read-only unless your task says otherwise. Keep outputs concise and evidence-backed (cite file paths / URLs).
