---
doc: scope
status: approved
---

# RECLAIM — Flight Cancellation & Refund Action Engine (Build With AI: Basics MVP)

One line: An evidence-grounded consumer justice workflow that takes a cancelled flight dispute from raw narrative to verified statutory refund claim with an explicit human approval gate.

## The Unique Kernel
Instead of generating generic legal chatbot text, RECLAIM grounds the grievance in exact, verified regulatory clauses (DGCA CAR Section 3 Series M Part IV and EU 261/2004), computes an explainable multi-objective utility score $U(a)$ balancing recovery benefit, resolution delay, and procedural risk, and enforces a cryptographically verifiable Human Approval Gate before dispatching the claim to the carrier or AirSewa.

## Who It's For
A consumer whose flight was abruptly cancelled and whose refund was refused or delayed by an airline, with no realistic legal assistance. Today, they either give up, vent helplessly on social media, or spend weeks emailing unresponsive customer care.

## The Core Loop
The user speaks or types their flight cancellation story ("My flight 6E-204 was cancelled 12 hours before departure and IndiGo refused my ₹7,500 refund"). RECLAIM splits and verifies the regulatory statutory text, calculates the exact refund + statutory compensation entitlement, optimizes the dispute path, displays the prepared action and consequences, and requests the user's explicit consent before executing the claim in a verified sandbox.

## Inspiration & Identity
- Principles from shared-context agent coordination systems, designed completely independently without Switch dependencies.
- Industrial, clean editorial aesthetic with high-contrast typography, warm cream canvas (`#fcfaf5`), and crisp borders.
- Inspired by public interest legal clinics and transparent consumer advocacy tools.

## Why This Matters to the Learner
Consumer disputes are inherently asymmetric: large corporations rely on consumer fatigue and boilerplate refusals. Giving everyday citizens statutory intelligence and an actionable execution pipeline levels the playing field.

## What "Working" Looks Like
A user inputs their flight cancellation details, the system splits the DGCA regulation preserving statutory citations like "Section 3.2", determines ₹17,500 total statutory recovery entitlement, ranks the direct claim path highest, prompts for human authorization, and dispatches the claim with a verified carrier tracking ID and audit trail.

## The POC Boundary
- **In Scope (Build With AI: Basics MVP)**:
  - Flight cancellation dispute vertical slice (`reclaim.connectors.aviation_refund`).
  - Recursive, regulation-aware text splitter (`POST /api/v1/split`) with 200 character budget enforcement, statutory token protection, and multilingual support.
  - Reclaim Decision Engine (`POST /api/v1/decision/optimize`) calculating normalized utility scores across candidate paths.
  - Action Approval Gate requiring explicit human authorization token before executing consequential actions.
  - Interactive Next.js dashboard modules for text splitting, connector execution, and decision optimization.
- **Later (Production Platform Roadmap)**:
  - Connectors for banking disputes (RBI Ombudsman), telecom, e-commerce, and real estate (RERA).
  - Cross-citizen institution radar backed by full Neo4j knowledge graph.
  - Automated WhatsApp/SMS status updates.
- **Explicitly Cut**:
  - Autonomous purchases or legal filings without user consent (strict security and ethical constraint).
  - Unverified LLM hallucinations pretending to be actual regulatory statutes.
