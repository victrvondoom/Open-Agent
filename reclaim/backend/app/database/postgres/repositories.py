from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database.supabase.client import get_supabase
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import Domain
from app.schemas.cases import CaseCreate, CaseStatus


class LocalRepositoryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("datasets") / "app_store"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, table: str) -> Path:
        return self.root / f"{table}.jsonl"

    def read(self, table: str) -> list[dict]:
        path = self.path(table)
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def upsert(self, table: str, key: str, row: dict) -> dict:
        rows = self.read(table)
        replaced = False
        for index, existing in enumerate(rows):
            if existing.get(key) == row.get(key):
                rows[index] = row
                replaced = True
                break
        if not replaced:
            rows.append(row)
        self.write(table, rows)
        return row

    def append(self, table: str, row: dict) -> dict:
        path = self.path(table)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        return row

    def append_many(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        path = self.path(table)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        return len(rows)

    def write(self, table: str, rows: list[dict]) -> None:
        path = self.path(table)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")


class CaseRepository:
    """Repository boundary for Supabase/Postgres with durable local fallback."""

    def __init__(self) -> None:
        self._cases: dict[str, dict] = {}
        self._documents: dict[str, dict] = {}
        self._events: list[dict] = []
        self._agent_runs: dict[str, dict] = {}
        self._appeals: dict[str, dict] = {}
        self._knowledge_sources: dict[str, dict] = {}
        self._knowledge_chunks: dict[str, dict] = {}
        self.local = LocalRepositoryStore()
        self.supabase = get_supabase()
        self._hydrate_local()

    def _hydrate_local(self) -> None:
        for row in self.local.read("cases"):
            row["domain"] = Domain(row["domain"]) if isinstance(row.get("domain"), str) else row.get("domain")
            row["status"] = CaseStatus(row["status"]) if isinstance(row.get("status"), str) else row.get("status")
            self._cases[row["id"]] = row
        self._documents = {row["document_id"]: row for row in self.local.read("case_documents")}
        self._events = self.local.read("case_events")
        self._agent_runs = {row["id"]: row for row in self.local.read("agent_runs")}
        self._appeals = {row["id"]: row for row in self.local.read("appeals")}
        self._knowledge_sources = {row["source_id"]: row for row in self.local.read("knowledge_sources")}
        self._knowledge_chunks = {row["chunk_id"]: row for row in self.local.read("knowledge_chunks")}

    def _jsonable(self, value):
        if isinstance(value, Domain) or isinstance(value, CaseStatus):
            return value.value
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value

    async def create_case(self, user_id: str, payload: CaseCreate, case_id: str | None = None) -> dict:
        case_id = case_id or str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": case_id,
            "user_id": user_id,
            "domain": payload.domain,
            "title": payload.title,
            "institution_name": payload.institution_name,
            "summary": payload.summary,
            "jurisdiction": payload.jurisdiction,
            "status": CaseStatus.INTAKE,
            "created_at": now,
            "updated_at": now,
        }
        self._cases[case_id] = record
        stored = self._jsonable(record)
        self.local.upsert("cases", "id", stored)
        await self.supabase.upsert("cases", stored, on_conflict="id")
        await self.add_event(case_id, {"actor": "user", "event_type": "case_created", "title": "Case created", "body": payload.summary})
        await knowledge_graph.upsert_case_graph(record)
        return record

    async def update_case_status(self, case_id: str, status: CaseStatus) -> dict | None:
        case = self._cases.get(case_id)
        if not case:
            return None
        case["status"] = status
        case["updated_at"] = datetime.now(timezone.utc).isoformat()
        stored = self._jsonable(case)
        self.local.upsert("cases", "id", stored)
        await self.supabase.upsert("cases", stored, on_conflict="id")
        return case

    _VAULT_TITLE = "Document Vault"

    async def get_or_create_vault_case(self, user_id: str, domain: Domain) -> dict:
        """A stable, lazily-created case per (user, domain) for documents
        uploaded from the Document Vault UI rather than a specific dispute
        case -- so uploading a file only ever requires picking a domain, not
        first filling out a full case-creation form (title/institution/
        summary), while every upload still has a real case to attach to
        (indexing, knowledge-graph registration, and storage paths all key
        off case_id)."""
        existing = [
            case for case in self._cases.values()
            if case["user_id"] == user_id and case["domain"] == domain and case.get("title") == self._VAULT_TITLE
        ]
        if existing:
            return existing[0]
        return await self.create_case(user_id, CaseCreate(
            domain=domain,
            title=self._VAULT_TITLE,
            institution_name="Not specified",
            summary=f"Documents uploaded to the {domain.value} document vault, not tied to a specific dispute case.",
        ))

    async def get_case(self, case_id: str, user_id: str) -> dict | None:
        case = self._cases.get(case_id)
        if case and case["user_id"] == user_id:
            return case
        rows = await self.supabase.select("cases", {"id": case_id, "user_id": user_id}, limit=1)
        if not rows:
            return None
        row = rows[0]
        row["domain"] = Domain(row["domain"])
        row["status"] = CaseStatus(row["status"])
        self._cases[row["id"]] = row
        return row

    async def seed_starter_cases_for_user(self, user_id: str, force: bool = False) -> list[dict]:
        if not force and any(c["user_id"] == user_id for c in self._cases.values()):
            return [c for c in self._cases.values() if c["user_id"] == user_id]

        now = datetime.now(timezone.utc).isoformat()
        starter_templates = [
            {
                "domain": Domain.HEALTH_INSURANCE,
                "title": "Star Health: Pre-existing Condition Exclusion Denial on Cataract Surgery",
                "institution_name": "Star Health & Allied Insurance",
                "summary": "Hospitalization and surgical claim of Rs 1,45,000 for bilateral cataract surgery rejected under Clause 4.2 pre-existing condition exclusion, despite uninterrupted 36-month policy tenure and treating surgeon medical certificate confirming acute onset.",
                "jurisdiction": "IN-DL",
                "status": CaseStatus.READY_FOR_APPROVAL,
                "confidence": 0.94,
                "citations": ["IRDAI Master Circular on Health Insurance (2024)", "Section 45 of Insurance Act 1938 (Incontestability Clause)", "National Consumer Commission Order RP/1429/2021"],
                "reasoning": "Policy has exceeded the 36-month moratorium period under IRDAI 2024 guidelines. Pre-existing exclusion cannot be invoked post 3 years of continuous renewal. Claim rejection violates Section 45.",
                "doc_name": "MaxHealthcare_Discharge_Summary.pdf",
                "doc_preview": "MAX SUPER SPECIALITY HOSPITAL. Patient Admitted: 14-May-2026. Diagnosis: Senile Cataract Bilateral. Procedure: Phacoemulsification with Foldable IOL. Total Hospital Charge: Rs 1,45,280. Physician: Dr. A.K. Sharma MS (Ophth).",
                "appeal_title": "Statutory Appeal to Insurance Ombudsman & Principal Grievance Officer",
                "appeal_body": "BEFORE THE HON'BLE INSURANCE OMBUDSMAN\\n\\nIN THE MATTER OF: Arbitrary Repudiation of Cataract Surgery Claim\\nPolicy No: SH-2024-998124\\nInsurer: Star Health and Allied Insurance Co. Ltd.\\n\\n1. FACTUAL BACKGROUND:\\nThe Complainant holds continuous Health Policy SH-2024-998124 since October 2023 without any break in coverage. On May 14, 2026, the Complainant underwent bilateral cataract surgery at Max Healthcare.\\n\\n2. GROUNDS OF APPEAL:\\nA. Violation of IRDAI Master Circular 2024: Waiting period cannot exceed 36 months of continuous coverage.\\nB. Incontestability under Section 45: Policy completed over 3 continuous policy years.\\nC. Treating Physician Certification confirms acute clinical necessity.\\n\\n3. PRAYER:\\nDirect Insurer to disburse Rs 1,45,000 along with statutory 9% p.a. penal interest.",
            },
            {
                "domain": Domain.BANKING,
                "title": "HDFC Bank: Duplicate UPI Debit Rs 5,000 Unreversed After T+1 Mandate",
                "institution_name": "HDFC Bank Ltd",
                "summary": "Double deduction of Rs 5,000 occurred during UPI QR payment at merchant terminal. The merchant settlement record confirms receipt of only single credit. Bank has failed to auto-reversal within the mandatory RBI T+1 timeline and refused penalty compensation.",
                "jurisdiction": "IN-MH",
                "status": CaseStatus.REVIEW_REQUIRED,
                "confidence": 0.92,
                "citations": ["RBI Circular DPSS.CO.PD No.629/02.01.014/2019-20 (Harmonisation of TAT and customer compensation)", "RBI Integrated Ombudsman Scheme 2021"],
                "reasoning": "RBI turn-around time mandate requires auto-reversal by T+1. Overdue by 12 days; customer is entitled to Rs 100/day compensation beyond turnaround time.",
                "doc_name": "HDFC_Account_Statement_June2026.pdf",
                "doc_preview": "HDFC BANK A/C STATEMENT. Date: 02-Jun-2026. Ref: UPI/61541098271. Debit: Rs 5,000.00. Ref: UPI/61541098272. Debit: Rs 5,000.00. Merchant: Freshmart Supermarket. Settlement: Single Credit.",
                "appeal_title": "Complaint to Banking Ombudsman for Turnaround Breach & Statutory Delay Compensation",
                "appeal_body": "BEFORE THE BANKING OMBUDSMAN (RESERVE BANK OF INDIA)\\n\\nCOMPLAINT UNDER RBI INTEGRATED OMBUDSMAN SCHEME 2021\\n\\n1. Dispute relates to unreversed duplicate UPI transaction of Rs 5,000 on 02-Jun-2026.\\n2. Merchant settlement certificate proves single receipt.\\n3. Bank failed to comply with RBI circular on customer compensation for failed transactions.\\n\\nRELIEF SOUGHT: Immediate reversal of Rs 5,000 plus Rs 1,200 delay compensation (Rs 100/day).",
            },
            {
                "domain": Domain.AIRLINES,
                "title": "IndiGo Flight 6E-241 Cancelled 2h Before Departure: Denied Refund & Care",
                "institution_name": "InterGlobe Aviation Ltd (IndiGo)",
                "summary": "Flight 6E-241 (BOM to DEL) cancelled 2 hours prior to scheduled departure. Carrier refused alternate flight on partner carriers, declined hotel accommodation, and issued an expiring travel credit note instead of statutory full cash refund.",
                "jurisdiction": "IN-DL",
                "status": CaseStatus.READY_FOR_APPROVAL,
                "confidence": 0.96,
                "citations": ["DGCA Civil Aviation Requirement (CAR) Section 3, Series M, Part IV", "Consumer Protection Act 2019 Section 2(47)"],
                "reasoning": "DGCA CAR Section 3 stipulates full refund within 7 days plus passenger compensation of Rs 10,000 for cancellation without 24h prior notification.",
                "doc_name": "IndiGo_Ticket_Confirmation_6E241.pdf",
                "doc_preview": "INDIGO E-TICKET. PNR: 6EQW89. Flight: 6E-241 BOM-DEL. Departure: 18:30. Status: Cancelled at 16:15. Voucher issued without consent.",
                "appeal_title": "Demand Notice & AirSewa Grievance under DGCA CAR Section 3",
                "appeal_body": "TO: APPELLATE AUTHORITY, INTERGLOBE AVIATION LTD & DGCA AIRSEWA\\n\\nSUBJECT: Demand for Statutory Passenger Compensation for Cancellation of Flight 6E-241\\n\\n1. Flight cancelled without statutory 24-hour advance notice.\\n2. Passenger was forced to accept voucher against explicit verbal and written refusal.\\n3. Claiming full ticket refund of Rs 8,450 + Rs 10,000 mandatory compensation under DGCA CAR Section 3.",
            },
            {
                "domain": Domain.TELECOM,
                "title": "Airtel: Postpaid Billed & Penalized 60 Days Post Documented Cancellation",
                "institution_name": "Bharti Airtel Ltd",
                "summary": "Postpaid fiber and SIM service cancelled with written confirmation on April 4, 2026. Airtel continued recurring monthly generation of Rs 1,178 plus late payment interest for two successive billing cycles.",
                "jurisdiction": "IN-KA",
                "status": CaseStatus.SUBMITTED,
                "confidence": 0.89,
                "citations": ["TRAI Telecom Consumers Protection Regulations (TCPR)", "Telecom Disputes Settlement and Appellate Tribunal (TDSAT) Rulings"],
                "reasoning": "TRAI regulations prohibit service provider billing past verified termination request confirmation date. Negative credit reporting threats are unlawful.",
                "doc_name": "Airtel_Cancellation_Receipt_SR9912.pdf",
                "doc_preview": "BHARTI AIRTEL SERVICE REQUEST ACKNOWLEDGEMENT. SR No: 991284918. Service: Broadband + Postpaid SIM. Status: Disconnected as per customer request. Date: 04-Apr-2026.",
                "appeal_title": "Appellate Grievance to Airtel Appellate Authority & TRAI PG Portal",
                "appeal_body": "TO THE APPELLATE AUTHORITY, BHARTI AIRTEL LTD\\n\\nREGARDING: Unlawful Post-Termination Billing for Connection No. 9811449182\\n\\n1. Service was formally surrendered and acknowledged on April 4, 2026.\\n2. Subsequent bills dated May 1 and June 1 are void ab initio.\\n3. Demand immediate billing cancellation and written confirmation of zero liability.",
            },
            {
                "domain": Domain.HOUSING,
                "title": "DLF Privana: 18-Month Delayed Possession & Withheld RERA Interest",
                "institution_name": "DLF Limited",
                "summary": "Builder failed to offer physical handover of 3BHK unit by scheduled completion date of December 2024. Promoter refuses to disburse monthly delay interest at SBI MCLR+2% under Section 18 of Real Estate (Regulation and Development) Act 2016.",
                "jurisdiction": "IN-HR",
                "status": CaseStatus.REVIEW_REQUIRED,
                "confidence": 0.93,
                "citations": ["RERA Act 2016 Section 18(1)", "Supreme Court of India: Newtech Promoters vs State of UP (2021)"],
                "reasoning": "Section 18 gives allottee absolute unconditional right to monthly interest until possession. Force majeure clauses cannot be extended arbitrarily.",
                "doc_name": "Builder_Buyer_Agreement_DLF.pdf",
                "doc_preview": "BUILDER BUYER AGREEMENT. Unit: Tower C, Flat 1402. Promised Delivery Date: 31-Dec-2024. Total Consideration Paid: Rs 1,84,00,000.",
                "appeal_title": "RERA Form M Complaint for Recovery of Statutory Delay Interest",
                "appeal_body": "BEFORE THE HARYANA REAL ESTATE REGULATORY AUTHORITY (HARERA)\\n\\nFORM M COMPLAINT UNDER SECTION 31 OF RERA ACT 2016\\n\\nCOMPLAINANT: Allottee Flat 1402 Tower C\\nRESPONDENT: DLF Limited\\n\\nGROUNDS: Promoter failed to deliver possession within committed tenure. Seeking monthly interest at SBI MCLR+2% from 01-Jan-2025 until actual handover.",
            },
            {
                "domain": Domain.ECOMMERCE,
                "title": "Amazon India: Counterfeit Sony WH-1000XM5 & Refusal of 7-Day Return",
                "institution_name": "Amazon Seller Services Pvt Ltd",
                "summary": "High-end headphones ordered under Prime delivery verified as counterfeit by authorized Sony Service Center. Amazon seller declined replacement or refund alleging item tampered by buyer.",
                "jurisdiction": "IN-KA",
                "status": CaseStatus.INTAKE,
                "confidence": 0.88,
                "citations": ["Consumer Protection (E-Commerce) Rules 2020", "Consumer Protection Act 2019 Section 2(9) and Section 2(47)"],
                "reasoning": "Marketplace platform shares joint liability for counterfeit goods sold through fulfilled channels under E-Commerce Rules 2020.",
                "doc_name": "Sony_Service_Center_Inspection_Certificate.pdf",
                "doc_preview": "SONY AUTHORIZED SERVICE CENTRE. Inspection Report. Model: WH-1000XM5. Serial No on box does not match internal PCB firmware ID. Unit confirmed non-genuine / counterfeit.",
                "appeal_title": "Legal Notice for Unfair Trade Practice & Product Liability Claim",
                "appeal_body": "FORMAL LEGAL NOTICE UNDER CONSUMER PROTECTION ACT 2019\\n\\nTo: Amazon Seller Services Pvt Ltd\\n\\nDemand for full refund of Rs 28,990 plus compensation for mental harassment regarding counterfeit electronic merchandise delivered on 10-Jun-2026.",
            },
            {
                "domain": Domain.GOVERNMENT,
                "title": "Regional Passport Office: Police Verification Stuck 90 Days Without Reason",
                "institution_name": "Ministry of External Affairs / Regional Passport Office",
                "summary": "Re-issue application File No. DL108492819 stuck at Police Verification stage for over 90 days despite spotless verification history, violating citizen charter SLA.",
                "jurisdiction": "IN-DL",
                "status": CaseStatus.ANALYZING,
                "confidence": 0.87,
                "citations": ["Passport Rules 1980", "Public Records Citizen Charter SLA Guidelines", "RTI Act 2005 Section 6(1)"],
                "reasoning": "Citizen Charter sets maximum SLA of 21 days for standard police verification. 90-day delay constitutes administrative deficiency.",
                "doc_name": "Passport_Application_Receipt_DL108.pdf",
                "doc_preview": "PASSPORT SEVA KENDRA RECEIPT. File No: DL108492819. Date of Application: 12-Mar-2026. Current Status: Pending with Police Station Enquiry since 15-Mar-2026.",
                "appeal_title": "CPGRAMS Grievance Petition to Joint Secretary (PSP) & Chief Passport Officer",
                "appeal_body": "PUBLIC GRIEVANCE UNDER CPGRAMS PORTAL\\n\\nMinistry of External Affairs (Consular, Passport & Visa Division)\\n\\nIssue: Unexplained delay of 90 days in processing passport re-issue File No DL108492819. Prayer for expeditious dispatch and police report clearance.",
            },
            {
                "domain": Domain.HEALTHCARE_PROVIDER,
                "title": "Max Super Speciality: Duplicate Room Tariff & Unitemized Consumables",
                "institution_name": "Max Super Speciality Hospital",
                "summary": "Hospital charged Rs 48,000 in unitemized surgical consumables and billed room tariff at both admission and discharge days contrary to Clinical Establishments Act and CGHS rates.",
                "jurisdiction": "IN-DL",
                "status": CaseStatus.READY_FOR_APPROVAL,
                "confidence": 0.91,
                "citations": ["Clinical Establishments (Registration and Regulation) Act", "National Consumer Disputes Redressal Commission (NCDRC) Overbilling Precedents"],
                "reasoning": "NCDRC guidelines prohibit charging room tariff twice for calendar day of admission and discharge when total duration is under 24 hours for that bracket.",
                "doc_name": "Max_Itemized_Hospital_Bill.pdf",
                "doc_preview": "MAX HEALTHCARE INVOICE. IP No: 449182. Room Rent: 14-May (Rs 12,000) & 15-May (Rs 12,000). Miscellaneous Consumables: Rs 48,200 (No breakdown provided). Total: Rs 1,45,280.",
                "appeal_title": "Complaint to Hospital Grievance Committee & State Directorate of Health Services",
                "appeal_body": "BEFORE THE DIRECTORATE GENERAL OF HEALTH SERVICES (DGHS)\\n\\nRE: Arbitrary and Inflated Hospital Billing by Max Super Speciality Hospital\\n\\nDemand for audit of unitemized consumables of Rs 48,200 and reimbursement of excess dual-day room rent charges.",
            },
        ]

        seeded_cases = []
        for template in starter_templates:
            case_id = str(uuid4())
            case_record = {
                "id": case_id,
                "user_id": user_id,
                "domain": template["domain"],
                "title": template["title"],
                "institution_name": template["institution_name"],
                "summary": template["summary"],
                "jurisdiction": template["jurisdiction"],
                "status": template["status"],
                "created_at": now,
                "updated_at": now,
            }
            self._cases[case_id] = case_record
            stored_case = self._jsonable(case_record)
            self.local.upsert("cases", "id", stored_case)
            seeded_cases.append(case_record)

            # Agent Run
            run_id = str(uuid4())
            run = {
                "id": run_id,
                "case_id": case_id,
                "workflow_name": "MultiDomainCaseWorkflow",
                "status": "completed",
                "input": {"case_id": case_id, "case_summary": template["summary"]},
                "output": {
                    "domain": template["domain"].value,
                    "confidence": template["confidence"],
                    "citations": template["citations"],
                    "reasoning": template["reasoning"],
                },
                "error": None,
                "created_at": now,
            }
            self._agent_runs[run_id] = run
            self.local.upsert("agent_runs", "id", self._jsonable(run))

            # Evidentiary Document
            doc_id = str(uuid4())
            doc = {
                "document_id": doc_id,
                "case_id": case_id,
                "user_id": user_id,
                "domain": template["domain"].value,
                "filename": template["doc_name"],
                "storage_path": f"cases/{template['domain'].value}/{template['doc_name']}",
                "indexed": True,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "pages_ocrd": 3,
                "text_chars": len(template["doc_preview"]) * 8,
                "text_preview": template["doc_preview"],
                "created_at": now,
            }
            self._documents[doc_id] = doc
            self.local.upsert("case_documents", "document_id", self._jsonable(doc))

            # Appeal Draft
            appeal_id = str(uuid4())
            appeal = {
                "id": appeal_id,
                "case_id": case_id,
                "user_id": user_id,
                "version": 1,
                "title": template["appeal_title"],
                "content": template["appeal_body"],
                "status": "submitted" if template["status"] == CaseStatus.SUBMITTED else "ready_for_approval" if template["status"] == CaseStatus.READY_FOR_APPROVAL else "draft",
                "domain": template["domain"].value,
                "created_at": now,
            }
            self._appeals[appeal_id] = appeal
            self.local.upsert("appeals", "id", self._jsonable(appeal))

            # Case Events
            for event_title, event_body in [
                ("Case opened", f"Consumer dispute registered against {template['institution_name']}"),
                (f"Document indexed: {template['doc_name']}", "OCR extracted & statutory evidence matched"),
                ("Multi-agent analysis completed", f"Specialist agent scored {int(template['confidence']*100)}% statutory confidence"),
                ("Legal appeal draft generated", template["appeal_title"]),
            ]:
                event_rec = {
                    "id": str(uuid4()),
                    "case_id": case_id,
                    "actor": "agent",
                    "event_type": "status_update",
                    "title": event_title,
                    "body": event_body,
                    "created_at": now,
                }
                self._events.append(event_rec)
                self.local.append("case_events", self._jsonable(event_rec))

        return seeded_cases

    async def list_cases(self, user_id: str, domain: Domain | None = None) -> list[dict]:
        user_cases = [case for case in self._cases.values() if case["user_id"] == user_id]
        if not user_cases and user_id:
            await self.seed_starter_cases_for_user(user_id)
            user_cases = [case for case in self._cases.values() if case["user_id"] == user_id]
        if domain:
            user_cases = [case for case in user_cases if case["domain"] == domain]
        return user_cases

    async def list_analyses_for_user(self, user_id: str) -> list[dict]:
        """Every case enriched with its agent-run results -- confidence,
        which domains were actually analyzed, and how many runs completed
        vs failed -- so "My Analyses" can show real status/confidence
        instead of just the raw case record."""
        cases = await self.list_cases(user_id)
        analyses = []
        for case in cases:
            runs = [run for run in self._agent_runs.values() if run["case_id"] == case["id"]]
            confidences = [
                run["output"]["confidence"] for run in runs
                if isinstance(run.get("output"), dict) and isinstance(run["output"].get("confidence"), (int, float))
            ]
            domains_involved = sorted({
                run["output"].get("domain") for run in runs
                if isinstance(run.get("output"), dict) and run["output"].get("domain")
            }) or [case["domain"].value if hasattr(case["domain"], "value") else case["domain"]]
            analyses.append({
                **self._jsonable(case),
                "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
                "run_count": len(runs),
                "completed_runs": sum(1 for run in runs if run.get("status") == "completed"),
                "domains_involved": domains_involved,
            })
        return sorted(analyses, key=lambda a: a.get("updated_at") or a.get("created_at") or "", reverse=True)

    async def add_document(self, document: dict) -> dict:
        document.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        self._documents[document["document_id"]] = document
        stored = self._jsonable(document)
        self.local.upsert("case_documents", "document_id", stored)
        supabase_document = {key: value for key, value in stored.items() if key not in {"document_id", "chunks_indexed"}}
        await self.supabase.upsert("case_documents", supabase_document, on_conflict="id")
        await self.add_event(
            document["case_id"],
            {
                "actor": "system",
                "event_type": "document_uploaded",
                "title": f"Document uploaded: {document['filename']}",
                "body": f"Indexed: {document.get('indexed', False)}",
            },
        )
        return document

    async def list_documents(self, case_id: str) -> list[dict]:
        return [document for document in self._documents.values() if document["case_id"] == case_id]

    async def list_documents_for_user(self, user_id: str) -> list[dict]:
        documents = [document for document in self._documents.values() if document["user_id"] == user_id]
        return sorted(documents, key=lambda d: d.get("created_at") or "", reverse=True)

    async def get_documents_by_ids(self, document_ids: list[str], user_id: str) -> list[dict]:
        """Fetch specific documents by id, scoped to `user_id` -- used to pull
        the exact set of documents a caller uploaded for one analysis run
        (regardless of which case/vault they're attached to), rather than
        every document ever uploaded to that domain's vault."""
        return [
            self._documents[document_id]
            for document_id in document_ids
            if document_id in self._documents and self._documents[document_id]["user_id"] == user_id
        ]

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        document = self._documents.get(document_id)
        if not document or document["user_id"] != user_id:
            return False
        del self._documents[document_id]
        self.local.write("case_documents", [self._jsonable(d) for d in self._documents.values()])
        await self.supabase.delete("case_documents", {"id": document_id})
        return True

    async def add_event(self, case_id: str, event: dict) -> dict:
        record = {"id": str(uuid4()), "case_id": case_id, "created_at": datetime.now(timezone.utc).isoformat(), **event}
        self._events.append(record)
        self.local.append("case_events", self._jsonable(record))
        await self.supabase.insert("case_events", self._jsonable(record))
        return record

    async def list_events(self, case_id: str) -> list[dict]:
        return [event for event in self._events if event["case_id"] == case_id]

    def _user_case_ids(self, user_id: str) -> set[str]:
        """Events don't carry user_id directly (several call sites -- e.g.
        add_agent_run -- don't have it in scope), so cross-case queries
        correlate via case_id instead: every case_id the user has any
        relationship with, across real Cases, appeals, and documents (the
        synthetic per-query case_ids from the multi-domain assistant
        workflow never create a real Case row, so appeals/documents are the
        only source of truth for those)."""
        ids = {case["id"] for case in self._cases.values() if case["user_id"] == user_id}
        ids |= {appeal["case_id"] for appeal in self._appeals.values() if appeal["user_id"] == user_id}
        ids |= {doc["case_id"] for doc in self._documents.values() if doc["user_id"] == user_id}
        return ids

    async def list_events_for_user(self, user_id: str, limit: int = 50, before: str | None = None) -> list[dict]:
        case_ids = self._user_case_ids(user_id)
        events = [event for event in self._events if event["case_id"] in case_ids]
        if before:
            events = [event for event in events if (event.get("created_at") or "") < before]
        return sorted(events, key=lambda e: e.get("created_at") or "", reverse=True)[:limit]

    async def add_agent_run(self, case_id: str, workflow_name: str, status: str, input_payload: dict, output_payload: dict, error: str | None = None) -> dict:
        run = {
            "id": str(uuid4()),
            "case_id": case_id,
            "workflow_name": workflow_name,
            "status": status,
            "input": input_payload,
            "output": output_payload,
            "error": error,
        }
        self._agent_runs[run["id"]] = run
        stored = self._jsonable(run)
        self.local.append("agent_runs", stored)
        await self.supabase.insert("agent_runs", stored)
        await self.add_event(case_id, {"actor": "agent", "event_type": "agent_run", "title": f"{workflow_name} finished", "body": status})
        return run

    async def list_agent_runs(self, case_id: str) -> list[dict]:
        return [run for run in self._agent_runs.values() if run["case_id"] == case_id]

    async def add_appeal(
        self, case_id: str, user_id: str, title: str, content: str,
        *, document_type: str = "appeal_letter", domain: str | None = None,
    ) -> dict:
        version = 1 + len([appeal for appeal in self._appeals.values() if appeal["case_id"] == case_id])
        appeal = {
            "id": str(uuid4()),
            "case_id": case_id,
            "user_id": user_id,
            "version": version,
            "title": title,
            "content": content,
            "status": "draft",
            # Denormalized so the cross-case Appeals Center (list_appeals_for_user)
            # never needs a join with `cases` -- appeals generated from the
            # multi-domain assistant workflow don't create a real Case row,
            # only a synthetic case_id for internal state tracking.
            "document_type": document_type,
            "domain": domain,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._appeals[appeal["id"]] = appeal
        self.local.append("appeals", self._jsonable(appeal))
        await self.supabase.insert("appeals", self._jsonable(appeal))
        await self.add_event(case_id, {"actor": "agent", "event_type": "appeal_drafted", "title": f"Appeal draft v{version} created", "body": title})
        return appeal

    async def list_appeals(self, case_id: str) -> list[dict]:
        return [appeal for appeal in self._appeals.values() if appeal["case_id"] == case_id]

    async def list_appeals_for_user(self, user_id: str) -> list[dict]:
        appeals = [appeal for appeal in self._appeals.values() if appeal["user_id"] == user_id]
        return sorted(appeals, key=lambda a: a.get("created_at") or "", reverse=True)

    async def update_appeal_status(self, appeal_id: str, user_id: str, status: str) -> dict | None:
        appeal = self._appeals.get(appeal_id)
        if not appeal or appeal["user_id"] != user_id:
            return None
        appeal["status"] = status
        self.local.upsert("appeals", "id", self._jsonable(appeal))
        await self.supabase.upsert("appeals", self._jsonable(appeal), on_conflict="id")
        await self.add_event(appeal["case_id"], {"actor": "user", "event_type": "appeal_status_changed", "title": f"Appeal marked {status}", "body": appeal["title"]})
        return appeal

    async def upsert_knowledge_source(self, source: dict) -> dict:
        self._knowledge_sources[source["source_id"]] = source
        stored = self._jsonable(source)
        self.local.upsert("knowledge_sources", "source_id", stored)
        await self.supabase.upsert("knowledge_sources", stored, on_conflict="source_id")
        return source

    async def add_knowledge_chunks(self, source_id: str, chunks: list[dict]) -> int:
        stored_chunks: list[dict] = []
        supabase_records: list[dict] = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or str(uuid4())
            record = {"chunk_id": chunk_id, "source_id": source_id, **chunk}
            self._knowledge_chunks[chunk_id] = record
            stored = self._jsonable(record)
            stored_chunks.append(stored)
            supabase_records.append({key: value for key, value in stored.items() if key != "chunk_id"})
        self.local.append_many("knowledge_chunks", stored_chunks)
        await self.supabase.upsert_many("knowledge_chunks", supabase_records, on_conflict="source_id,chunk_index")
        return len(chunks)

    async def list_knowledge_sources(self, domain: Domain | None = None) -> list[dict]:
        rows = list(self._knowledge_sources.values())
        if domain:
            rows = [source for source in rows if source.get("domain") == domain.value]
        return rows

    async def list_knowledge_chunks(self, source_id: str | None = None, limit: int = 100) -> list[dict]:
        rows = list(self._knowledge_chunks.values())
        if source_id:
            rows = [chunk for chunk in rows if chunk.get("source_id") == source_id]
        return rows[:limit]


case_repository = CaseRepository()

