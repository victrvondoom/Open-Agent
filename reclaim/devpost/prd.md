---
doc: prd
status: approved
---

# RECLAIM — Product Requirements Document (PRD)

One line: An evidence-aware consumer justice and dispute resolution engine that transforms raw consumer claims into verified, statutory actions with explicit human approval.
Source: `scope.md > The Unique Kernel`.

## The Core Journey
1. **Arrival**: The consumer lands on RECLAIM and sees the brand promise: *"From problem to proof to resolution."*
2. **Grievance Input**: The user dictates or types a dispute (e.g., flight cancellation with denied refund).
3. **Regulation-Aware Segmentation**: The system runs recursive text segmentation on relevant airline regulations (DGCA CAR Series M Part IV & EU 261/2004), preserving legal numbering like "Section 3.2" and enforcing chunk budget limits.
4. **Evidence & Eligibility Scoring**: The system extracts statutory facts (flight number, cancellation timing, amount paid), verifies entitlement (refund + statutory delay compensation), and flags missing evidence.
5. **Multi-Objective Decision Ranking**: The Reclaim Decision Engine computes normalized utility $U(a) = w_1 B(a) - w_2 C(a) - w_3 D(a) - w_4 R(a) - w_5 P(a)$ across candidate paths (Direct Claim vs. AirSewa Escalation vs. Consumer Court).
6. **Action Formulation**: The prepared action is formatted with plain-language summary, estimated benefit, and non-reversible consequence warnings.
7. **Human Approval Gate**: The user explicitly reviews and clicks "Authorize Claim Submission", generating a secure approval token.
8. **Action Execution & Tracking**: The connector executes in verified sandbox mode, returns an authoritative carrier claim reference, and provides live status tracking and reconciliation.

## Screens and Layout
- **Landing Page (`/`)**: Introduces RECLAIM, live metrics, and quick flight dispute scenarios.
- **Universal Case Intake (`/dashboard/new`)**: Voice and text entry with live telemetry.
- **Action Fabric & Connector Center (`/dashboard/connectors`)**: Registry of available connectors, sandbox health, and action preparation.
- **Regulatory Text Splitter Inspector (`/dashboard/text-splitter`)**: Developer & user inspector demonstrating recursive splitting, character budgets, and legal citations.
- **Decision Engine Optimizer (`/dashboard/decision-optimizer`)**: Visual utility ranking displaying benefit, delay, risk, and constraint evaluations.

## Look and Feel
- Warm editorial cream canvas (`#fcfaf5`), deep charcoal typography (`#1c1917`), amber accents (`#f59e0b`), and sharp 2px solid neo-brutalist borders.
- Typography: Figtree for clear sans-serif UI, EB Garamond for legal document previews, JetBrains Mono for statutory citations and telemetry.
- No distracting generic gradients; clean, authoritative, accessible controls.

## Features and Behavior

### 1. Aviation Refund Action Fabric Connector
- User Story: As an aggrieved passenger, I want to calculate my statutory refund entitlement and file an official claim so that the carrier must respond within 14 days.
  - [x] Evaluates DGCA CAR Series M Part IV rules for cancellations < 24 hrs prior to departure.
  - [x] Computes ticket refund + statutory compensation (up to ₹10,000 / €250).
  - [x] Generates prepared claim package with PNR and passenger telemetry.

### 2. Explicit Human Approval Gate
- User Story: As a consumer, I want full control over consequential filings so that no system executes actions on my behalf without my explicit informed consent.
  - [x] Requires human authorization token for all write operations (`submit_airline_claim`, `escalate_dgca_airsewa`).
  - [x] Blocks unauthorized execution with strict 403 Forbidden.
  - [x] Enforces token single-use (replay attack prevention).

### 3. Recursive Regulation Text Splitter
- User Story: As an evidence analyst, I want legal regulations segmented without breaking statutory identifiers so that citations point to exact passages.
  - [x] Fallback chain: `["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]`.
  - [x] Protects tokens like "Section 3.2", "Part IV", and currency amounts.
  - [x] Guarantees maximum chunk size budget (e.g. 200 chars).
  - [x] Preserves Unicode (English, Tamil, Hindi).

### 4. Mathematical Decision Engine
- User Story: As a consumer, I want to see the best next step based on cost, delay, and risk so that I do not waste months on the wrong legal path.
  - [x] Evaluates candidate paths: Direct Carrier Claim vs. AirSewa Escalation vs. DCDRC Court Filing.
  - [x] Normalizes metrics on $[0, 1]$ and enforces statutory deadline constraints.

## What We're Building
- Complete end-to-end flight cancellation dispute vertical slice.
- Production-ready FastAPI routes for splitting, connectors, and decision optimization.
- Next.js dashboard modules with live interaction.
- Verified test suite with 100% pass rate.

## Deferred From the POC
- Multi-party escrow refund transfers.
- Real court filing electronic signatures (e-Filing portal integration).
- Full cross-institutional dispute aggregation across hundreds of banks and airlines.

## Non-Goals
- Autonomous AI legal representation in a courtroom.
- Automated financial transactions without banking authorization.
