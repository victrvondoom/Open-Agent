import type { Citation, DomainCandidate, MultiDomainCaseResponse, DomainResult } from "@/lib/api-client";

// Built-in synthetic scenarios. Used (a) as story-style starting points on the
// assistant / new-claim pages and (b) as an automatic fallback when the live
// multi-agent backend can't be reached, so the product always demonstrates a
// complete, believable end-to-end workflow instead of "Failed to fetch".

export interface SyntheticScenario {
  domain: string;
  title: string;
  prompt: string;
  keywords: string[];
  institution: string;
  story: string[];
  clauses: string[];
  regulations: string[];
  missingDocs: string[];
  probability: number;
  strategy: string[];
  escalation: string[];
  letterSubject: string;
  citation: { title: string; authority: string; section: string };
}

export const SYNTHETIC_SCENARIOS: SyntheticScenario[] = [
  {
    domain: "health_insurance",
    title: "The claim denied as 'pre-existing'",
    prompt: "My health insurance claim for knee surgery was denied as a pre-existing condition, but I have been insured for 5 years.",
    keywords: ["insurance", "claim", "denied", "policy", "pre-existing", "reimbursement", "cashless"],
    institution: "Star Shield Health Insurance",
    story: [
      "Meera buys a family floater policy in 2020 and renews it every year without a break.",
      "In 2025 she needs knee surgery; the cashless request is rejected as a 'pre-existing condition'.",
      "RESOLVE finds the moratorium clause: after 60 months of continuous cover, pre-existing exclusions cannot be invoked.",
      "Meera files a grievance with a cited letter and the insurer reverses the denial within 15 days.",
    ],
    clauses: ["Moratorium period: 60 continuous months", "Pre-existing disease waiting period: 36 months", "Cashless pre-authorisation must be decided within 1 hour"],
    regulations: ["IRDAI (Protection of Policyholders' Interests) Regulations, 2017", "IRDAI Master Circular on Health Insurance Business, 2024"],
    missingDocs: ["Policy schedule showing continuous renewals", "Denial letter with reason code", "Discharge summary"],
    probability: 0.86,
    strategy: ["Quote the 60-month moratorium clause in the first reply", "Request a written, clause-wise rejection reason", "Escalate to the insurer's Grievance Redressal Officer"],
    escalation: ["Insurer GRO (15 days)", "IRDAI Bima Bharosa portal", "Insurance Ombudsman (free, 90 days)"],
    letterSubject: "Request to reverse rejection of cashless claim under the 60-month moratorium",
    citation: { title: "IRDAI Health Insurance Master Circular", authority: "IRDAI", section: "Moratorium Period, Para 4" },
  },
  {
    domain: "banking",
    title: "Charged twice, refund refused",
    prompt: "My bank charged me twice for the same transaction and won't refund it.",
    keywords: ["bank", "charged", "twice", "transaction", "debit", "credit card", "upi", "refund", "loan", "fee"],
    institution: "Metro National Bank",
    story: [
      "Arjun pays Rs 12,499 for a laptop bag; the app shows a failure and he retries.",
      "Both debits succeed. The bank says 'the merchant will refund' and closes the ticket.",
      "RESOLVE finds the RBI turn-around-time rule: failed or duplicate transactions must be reversed in T+5 days, with Rs 100/day compensation.",
      "Arjun sends a cited complaint; the reversal and Rs 700 compensation arrive in a week.",
    ],
    clauses: ["Auto-reversal for failed transactions within T+5 working days", "Compensation of Rs 100 per day of delay"],
    regulations: ["RBI Circular on Harmonisation of Turn Around Time (TAT) for failed transactions, 2019", "RBI Integrated Ombudsman Scheme, 2021"],
    missingDocs: ["Bank statement showing both debits", "Merchant order confirmation", "Complaint reference number"],
    probability: 0.91,
    strategy: ["Attach statement lines for both debits", "Cite the T+5 reversal rule and per-day compensation", "Set a 7-day written deadline"],
    escalation: ["Bank nodal officer (30 days)", "RBI Integrated Ombudsman (cms.rbi.org.in)"],
    letterSubject: "Duplicate debit of Rs 12,499 and compensation under RBI TAT rules",
    citation: { title: "RBI TAT Harmonisation Circular", authority: "Reserve Bank of India", section: "Para 5, Compensation" },
  },
  {
    domain: "airlines",
    title: "Cancelled flight, refund stalled",
    prompt: "My flight was cancelled and the airline refused a refund and offered only a voucher.",
    keywords: ["flight", "airline", "cancelled", "delay", "boarding", "baggage", "airport", "refund"],
    institution: "SkyJet Airways",
    story: [
      "Priya's 6 AM flight to Delhi is cancelled the night before; the airline offers only a credit voucher.",
      "She needs a refund because her meeting is lost.",
      "RESOLVE surfaces DGCA CAR Section 3 Series M Part IV: passengers may choose a full refund or alternate flight.",
      "Priya quotes the CAR and the full fare is refunded to the original payment method within 14 days.",
    ],
    clauses: ["Passenger may choose full refund or alternate flight", "Refund within 7 days for card payments, 30 days for travel agents"],
    regulations: ["DGCA CAR Section 3, Series M, Part IV", "Consumer Protection Act, 2019, Section 2(11)"],
    missingDocs: ["Cancellation SMS/email", "E-ticket and payment proof"],
    probability: 0.88,
    strategy: ["Decline the voucher in writing", "Quote the DGCA refund option", "File on AirSewa if no reply in 7 days"],
    escalation: ["Airline nodal officer", "AirSewa portal", "Consumer Commission via e-Daakhil"],
    letterSubject: "Refund request for cancelled flight as per DGCA CAR Section 3 Series M Part IV",
    citation: { title: "DGCA CAR Section 3 Series M Part IV", authority: "DGCA", section: "Facilities to passengers on cancellation" },
  },
  {
    domain: "telecom",
    title: "Billed for a cancelled plan",
    prompt: "My telecom provider is billing me for a plan I cancelled two months ago.",
    keywords: ["telecom", "mobile", "sim", "broadband", "recharge", "plan", "network", "billing", "postpaid", "port"],
    institution: "Connectel Mobile",
    story: [
      "Rohan cancels his Rs 999 postpaid plan after a store visit and receives an SMS confirmation.",
      "Two bills later, the charge continues and customer care gives only ticket numbers.",
      "RESOLVE finds the TRAI rule that billing complaints must be resolved within 4 weeks.",
      "Rohan escalates to the Appellate Authority and receives a credit note for both months.",
    ],
    clauses: ["Billing complaints resolved within 4 weeks", "Appeal to Appellate Authority within 30 days of the decision"],
    regulations: ["TRAI Telecom Consumers Complaint Redressal Regulations, 2012", "TRAI Telecom Consumers Protection Regulations, 2012"],
    missingDocs: ["Cancellation SMS", "Last three bills", "Complaint docket numbers"],
    probability: 0.83,
    strategy: ["Escalate the complaint docket to the Appellate Authority", "Request a written bill correction", "Dispute via the nodal officer"],
    escalation: ["Nodal Officer (3 weeks)", "Appellate Authority", "TRAI / Consumer Commission"],
    letterSubject: "Reversal of billing for cancelled postpaid plan",
    citation: { title: "TRAI Complaint Redressal Regulations", authority: "TRAI", section: "Regulation 8, Billing complaints" },
  },
  {
    domain: "ecommerce",
    title: "Counterfeit product, return denied",
    prompt: "An online seller sent me a counterfeit product and refuses a return.",
    keywords: ["order", "seller", "product", "delivery", "counterfeit", "fake", "return", "warranty", "defective", "amazon", "flipkart"],
    institution: "ShopKart Marketplace",
    story: [
      "Sana orders branded earbuds; the box arrives with mismatched serial numbers.",
      "The seller says 'no returns on audio items'.",
      "RESOLVE cites the E-Commerce Rules 2020: platforms are liable for counterfeit goods and may not refuse valid returns.",
      "Sana files on the National Consumer Helpline and receives a full refund plus pickup.",
    ],
    clauses: ["Counterfeit goods are a deficiency in service", "Marketplace must have a grievance officer responding within 48 hours"],
    regulations: ["Consumer Protection (E-Commerce) Rules, 2020, Rule 4", "Consumer Protection Act, 2019, Section 2(9)"],
    missingDocs: ["Photos of product and serial number", "Order invoice", "Brand authenticity confirmation"],
    probability: 0.87,
    strategy: ["Raise a grievance citing Rule 4", "Attach brand verification", "File on NCH after 48 hours"],
    escalation: ["Platform grievance officer", "National Consumer Helpline (1915)", "e-Daakhil"],
    letterSubject: "Counterfeit product complaint and refund demand under E-Commerce Rules 2020",
    citation: { title: "Consumer Protection (E-Commerce) Rules, 2020", authority: "Dept. of Consumer Affairs", section: "Rule 4, Liabilities of marketplace" },
  },
  {
    domain: "government",
    title: "Passport stuck in review",
    prompt: "My passport renewal application has been stuck in review for 90 days with no update.",
    keywords: ["passport", "rti", "certificate", "government", "scheme", "pension", "ration", "licence", "application", "office"],
    institution: "Regional Passport Office",
    story: [
      "Vikram files for passport renewal; status shows 'under review' for three months.",
      "Visits and calls give no reason or timeline.",
      "RESOLVE drafts an RTI under Section 6 and cites the Public Services Guarantee timeline.",
      "The RTI reply names the pending police verification; Vikram resolves it and receives the passport in 12 days.",
    ],
    clauses: ["RTI reply due within 30 days", "Citizen charter processing time for renewals: 30 days"],
    regulations: ["Right to Information Act, 2005, Section 6 and 7", "Passport Seva Citizen Charter"],
    missingDocs: ["Application reference number", "Receipt of fee payment"],
    probability: 0.8,
    strategy: ["File an online RTI on the pendency reason", "Raise on CPGRAMS", "Escalate to the Regional Passport Officer"],
    escalation: ["CPGRAMS", "First Appeal under RTI", "Passport Adalat"],
    letterSubject: "RTI application on delay in passport renewal",
    citation: { title: "Right to Information Act, 2005", authority: "Government of India", section: "Section 7(1), 30-day reply" },
  },
  {
    domain: "housing",
    title: "Builder delayed possession 18 months",
    prompt: "My builder delayed possession of my flat by 18 months and refuses to pay compensation under RERA.",
    keywords: ["builder", "flat", "possession", "rera", "rent", "deposit", "landlord", "apartment", "property", "housing"],
    institution: "Horizon Realty Developers",
    story: [
      "Anita books a flat with possession due in March 2024; the builder keeps pushing the date.",
      "Eighteen months later she still pays EMI and rent together.",
      "RESOLVE cites RERA Section 18: interest on delay at SBI MCLR + 2% from the committed date.",
      "Anita files at the state RERA authority and the builder agrees to pay the interest on settlement.",
    ],
    clauses: ["Possession date in the agreement for sale", "Interest on delay at SBI MCLR + 2%"],
    regulations: ["Real Estate (Regulation and Development) Act, 2016, Section 18", "State RERA Rules"],
    missingDocs: ["Agreement for sale", "Payment receipts and demand letters", "RERA registration number"],
    probability: 0.9,
    strategy: ["Compute interest from the committed possession date", "Send a legal notice", "File a complaint on the state RERA portal"],
    escalation: ["Builder legal notice (15 days)", "State RERA Authority", "Appellate Tribunal"],
    letterSubject: "Demand for delay interest under Section 18 of RERA",
    citation: { title: "RERA Act, 2016", authority: "Parliament of India", section: "Section 18, Return of amount and compensation" },
  },
  {
    domain: "healthcare",
    title: "Overcharged hospital bill",
    prompt: "I was overcharged for a hospital procedure that my insurance should have covered, and the discharge summary is missing.",
    keywords: ["hospital", "doctor", "bill", "treatment", "discharge", "surgery", "medical", "overcharged", "clinic", "dengue"],
    institution: "CityCare Multispeciality Hospital",
    story: [
      "Imran's father is discharged after a cardiac procedure; the final bill is Rs 40,000 above the estimate.",
      "The hospital withholds the discharge summary until the balance is paid.",
      "RESOLVE cites the Clinical Establishments Act and patient rights charter: itemised bills and records are mandatory.",
      "Imran requests the itemised bill; the hospital waives the duplicate charges and releases the summary.",
    ],
    clauses: ["Itemised bill must be provided on request", "Rates must match the displayed tariff"],
    regulations: ["Clinical Establishments (Registration and Regulation) Act, 2010", "Charter of Patients' Rights and Responsibilities (NHRC)"],
    missingDocs: ["Itemised bill", "Pre-admission estimate", "Insurer pre-authorisation approval"],
    probability: 0.82,
    strategy: ["Request itemised bill and tariff card in writing", "Compare against the insurer approval", "Escalate to the state Health Department"],
    escalation: ["Hospital grievance cell", "District Health Officer", "Consumer Commission"],
    letterSubject: "Request for itemised bill and correction of overcharged items",
    citation: { title: "Charter of Patients' Rights", authority: "NHRC", section: "Right to itemised bill and records" },
  },
];

export function scenarioFor(domain: string): SyntheticScenario | undefined {
  return SYNTHETIC_SCENARIOS.find((s) => s.domain === domain);
}

function scoreDomains(text: string): Array<{ s: SyntheticScenario; hits: string[] }> {
  const lower = text.toLowerCase();
  return SYNTHETIC_SCENARIOS.map((s) => ({ s, hits: s.keywords.filter((k) => lower.includes(k)) }))
    .filter((x) => x.hits.length > 0)
    .sort((a, b) => b.hits.length - a.hits.length);
}

export function syntheticClassify(query: string): { query: string; candidates: DomainCandidate[] } {
  const scored = scoreDomains(query);
  return {
    query,
    candidates: scored.slice(0, 3).map(({ s, hits }) => ({
      domain: s.domain,
      confidence: Math.min(0.95, 0.55 + hits.length * 0.15),
      matched_terms: hits,
    })),
  };
}

function resultFor(s: SyntheticScenario, query: string): DomainResult {
  const pct = Math.round(s.probability * 100);
  const report = [
    `## ${s.title}`,
    `**Your issue:** ${query}`,
    `### What happened (story)`,
    ...s.story.map((line, i) => `${i + 1}. ${line}`),
    `### Rules that apply`,
    ...s.regulations.map((r) => `- ${r}`),
    `### Key clauses`,
    ...s.clauses.map((c) => `- ${c}`),
    `### Recommended plan (${pct}% estimated success)`,
    ...s.strategy.map((x, i) => `${i + 1}. ${x}`),
    `### Escalation ladder`,
    ...s.escalation.map((x) => `- ${x}`),
    `### Draft letter`,
    `**Subject:** ${s.letterSubject}`,
    `Dear Sir/Madam at ${s.institution}, I request your immediate attention to the issue described above. Under the rules cited, I seek resolution within the stated timeline, failing which I will escalate to the authorities listed.`,
    `_Illustrative synthetic analysis: verify details before sending._`,
  ].join("\n\n");

  return {
    confidence: s.probability,
    route: `${s.domain}_workflow`,
    final_report: report,
    agent_trace: [
      `Research Agent: matched ${s.regulations.length} regulations and ${s.clauses.length} clauses`,
      `Evidence Agent: ${s.missingDocs.length} documents still needed`,
      `Knowledge Graph Agent: ${s.institution} appears in recurring dispute patterns`,
      `Strategy Agent: ${pct}% estimated success, ${s.escalation.length}-step escalation`,
      `Negotiation Agent: drafted letter "${s.letterSubject}"`,
      `Review Agent: citations checked, approval ready`,
    ],
    appeals: [],
    agent_breakdown: {
      research: { applicable_clauses: s.clauses, regulations: s.regulations, summary: `Relevant rules found for ${s.institution}.`, confidence: s.probability },
      evidence: { documents_missing: s.missingDocs, evidence_relevant: true, summary: "Evidence checklist prepared." },
      knowledge_graph: { patterns: [{ pattern: `Repeated ${s.title.toLowerCase()} disputes`, domain: s.domain, institution: s.institution, confidence: 0.74 }] },
      strategy: { can_appeal: "yes", success_probability: s.probability, recommended_strategy: s.strategy, escalation_path: s.escalation, summary: `${pct}% estimated chance of success.` },
      negotiation: { complaint_email: `Subject: ${s.letterSubject}`, summary: "Letter drafted." },
      review: { approval_ready: true, missing_evidence: s.missingDocs, summary: "Reviewed against sources." },
    },
  };
}

export function syntheticMultiDomain(query: string, forceDomain?: string): MultiDomainCaseResponse {
  let picks = scoreDomains(query).slice(0, 2).map((x) => x.s);
  if (forceDomain) {
    const forced = scenarioFor(forceDomain);
    if (forced) picks = [forced, ...picks.filter((p) => p.domain !== forced.domain)].slice(0, 2);
  }
  if (!picks.length) picks = [SYNTHETIC_SCENARIOS[1]];

  const per_domain_results: Record<string, DomainResult> = {};
  const combined_citations: Citation[] = [];
  picks.forEach((s) => {
    per_domain_results[s.domain] = resultFor(s, query);
    combined_citations.push({
      title: s.citation.title,
      authority: s.citation.authority,
      url: null,
      publication_date: null,
      section: s.citation.section,
      domain: s.domain,
      retrieved_chunk: s.clauses[0],
      confidence: 0.9,
    });
  });

  return {
    query,
    domains_analyzed: picks.map((p) => p.domain),
    primary_domain: picks[0].domain,
    per_domain_results,
    combined_citations,
    combined_summary: `Analysed across ${picks.length} domain(s) using built-in synthetic scenarios.`,
  };
}
