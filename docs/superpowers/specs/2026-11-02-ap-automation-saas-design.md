# Design: Indian Mid-Market AP Automation SaaS ("Working name: SmartAP India")

**Date:** 2026-11-02
**Status:** Approved design — ready for implementation planning
**Audience:** Dev crew (self-contained; no prior chat context required)

---

## 1. Overview

A commercial multi-tenant SaaS that automates the Accounts Payable invoice-to-post
workflow for Indian mid-market companies. v1 covers **capture → extraction →
compliance → matching → approval → ERP posting**. Payment execution is v2.

**Positioning (the moat):** Global AP tools (Stampli, Tipalti, Medius) have strong
AI/UX but no India compliance. Indian tools (Clear AP, TYASuite, IQInvoice) have
compliance but weak AI/UX. This product runs a **native India compliance gate on
the same data pipeline** as a modern AI-driven invoice workflow — the only
position that beats Clear on experience AND Stampli on compliance.

**Target customer:** Indian mid-market (₹50k–2L/month ACV), ERP-run companies
(manufacturing, trading, services). Beachhead ERP: SAP Business One + generic
bridge for everyone else.

**Team model:** 1 developer + AI-assisted development. Design biases toward
managed services, proven boring tech, and clear module boundaries.

---

## 2. Competitive Study — What We Borrow

| Source | Borrowed feature |
|---|---|
| Stampli | Invoice-centric collaboration (comments/questions/approvals ON the invoice); learning coding assistant; free approver access |
| Tipalti | Vendor self-service onboarding portal (v2); predictive GL coding |
| Medius | Touchless-processing ambition; drag-and-drop workflow builder |
| BILL | Approve via email without login |
| Nanonets | Template-free AI extraction; API-first design |
| OneFinOps | Line-level matching with tolerances; variance categorization; nightly GSTR-2B fetch; TDS at line level; vendor risk (v2) |
| Clear AP / TYASuite | 60+ configurable validation rules; MSME 43B(h) tracking; vendor correction portal (v2) |
| IQInvoice | Compliance gate on the same pipeline (not middleware); IRN validation at ingestion |

**India compliance essentials (statutory, non-negotiable for mid-market buyers):**
1. Native GSTR-2B pull + invoice-level ITC reconciliation
2. TDS automation (section-wise rates, withholding, Form 16A prep)
3. MSME 43B(h) guard (Udyam flagging, 15/45-day payment windows)
4. Multi-GSTIN routing
5. IRN + QR validation at ingestion
6. Deep ERP connector (mitigated: SAP B1 first + generic bridge)

**Regulatory notes to encode as data, not code:**
- Income-tax Act 2025 renumbers TDS sections effective 1 Apr 2026 (e.g., 194C/194J/194H consolidated under Section 393). TDS rate tables must be versioned data.
- E-invoicing: taxpayers with AATO ≥ ₹10 Cr must report e-invoices within 30 days of invoice date (effective Apr 2025). Surface this in compliance checks.
- GST API access goes through a GSP (GST Suvidha Provider) channel.

---

## 3. Feature List

### v1 (MVP)

**1. Invoice Capture & Intake**
- Multi-channel: per-company email inbox, drag-drop/bulk upload, REST API, SFTP
- Formats: PDF, scanned images, photos, and **IRP-signed e-invoice JSON** (parsed deterministically — no OCR)
- Duplicate detection at intake (content hash + fuzzy vendor/invoice-no/amount)

**2. AI Extraction & Validation**
- Hybrid LLM extraction: multimodal LLM → structured JSON → per-field confidence
- Vendor template cache: repeat vendors skip LLM after 2–3 confirmations
- Learning coding assistant: suggests GL code, cost center, TDS section from history
- Line-item extraction (header + lines)
- Human review queue: only low-confidence fields highlighted inline on the invoice image

**3. India Compliance Gate** (same pipeline; runs before approval, before ERP)
- GSTIN validation against live GSTN (block suspended/cancelled)
- IRN + QR verification against IRP at ingestion
- PAN + MCA registry checks (flag struck-off/blacklisted vendors)
- Native GSTR-2B pull (via GSP) + invoice-level ITC reconciliation, nightly; "ITC at risk" per bill; one-click vendor follow-up
- TDS engine: versioned section/rate tables, threshold tracking, challan due-date alerts
- MSME 43B(h) guard: Udyam auto-identification, 15/45-day countdown, breach escalation
- Multi-GSTIN routing by supply location/entity
- ~25 core validation rules at launch, user-extensible toward 60+ (rules as data)

**4. Matching Engine**
- Line-level 2-way (invoice↔PO) and 3-way (invoice↔PO↔GRN) with per-vendor/per-item tolerances
- Variance categorization: price / quantity / tax / freight
- Non-PO invoices: AI validates against rules + auto-assigns GL codes
- Exception queue with resolution paths (buyer / receiver / AP)

**5. Approval Workflow**
- Drag-and-drop workflow builder (rules by amount, vendor, GL, entity)
- Approve via email without login (web fallback)
- Comments, questions, attachments live on the invoice
- Auto-reminders + escalation; immutable audit trail

**6. ERP Integration**
- Generic bridge: CSV/REST import-export + mapping UI (day-one coverage for any ERP)
- SAP Business One native connector (Service Layer)
- Sync: vendors/POs/GRNs/GL in; approved bills out; payment status back
- Connector SDK: one `ErpConnector` interface; new ERPs = adapter + config

**7. Dashboards (basic)**
- AP queue, aging, touchless rate, exception count, ITC-at-risk, TDS quarterly summary, MSME countdown

**8. Platform & Security**
- Multi-tenant with tenant isolation (Postgres RLS) from day one
- RBAC (admin, ap_team, approver, viewer), 7-year audit retention, DPDP Act 2023 alignment
- Cloud SaaS default (AWS Mumbai); VPC/on-prem is a later packaging decision, not a rewrite

### v2 (deferred, additive — not structural)
- WhatsApp intake + approvals; vendor self-service portal (KYC, status, corrections)
- Payment execution (bank APIs: RazorpayX/ICICI/HDFC; NEFT/RTGS/IMPS/UPI; MSME-priority payment ordering)
- Advanced analytics (payment runway, vendor risk scores, close tracker)
- More ERP connectors (Dynamics 365, NetSuite, Busy, Marg, Zoho Books); SSO/SCIM; VPC packaging

---

## 4. Architecture

### Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python + FastAPI | Best AI/LLM ecosystem; async; typed; AI-assisted dev friendly |
| Frontend | Next.js + TypeScript | Invoice-centric UI; single web codebase |
| Database | PostgreSQL | RLS for tenant isolation; JSONB for flexible invoice schemas |
| Async jobs | Redis + ARQ | Extraction, nightly GSTR-2B, compliance checks, reminders (lighter than Celery; sufficient for MVP job types) |
| File storage | S3-compatible (S3/MinIO) | Invoice images, signed e-invoice JSONs |
| LLM | Provider-agnostic adapter | Gemini primary → GPT-4o/Claude fallback; swap without code change |
| Deployment | Docker Compose → AWS Mumbai | Same containers run in customer VPC later |

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│  Web App (Next.js)          Notifications (email/WA)    │
└──────────────┬──────────────────────────┬───────────────┘
               │ REST API                 │
┌──────────────▼──────────────────────────▼───────────────┐
│                    CORE API (FastAPI)                    │
│  tenants · invoices · vendors · workflows · audit log   │
└──┬──────────┬──────────┬──────────┬──────────┬──────────┘
   │          │          │          │          │
┌──▼───┐  ┌───▼────┐  ┌──▼─────┐  ┌─▼──────┐  ┌▼─────────┐
│INTAKE│  │EXTRACT │  │COMPLI- │  │MATCHING│  │ERP       │
│svc   │→ │pipeline│→ │ANCE    │→ │engine  │→ │CONNECTORS│
│email │  │LLM+conf│  │GATE    │  │2/3-way │  │bridge +  │
│upload│  │+cache  │  │rules+  │  │+toler. │  │SAP B1    │
│API   │  │        │  │GST APIs│  │        │  │          │
└──────┘  └────────┘  └────────┘  └────────┘  └──────────┘
        All async steps run on Redis workers
```

Each component is independently buildable and testable behind a defined interface.

### Data Flow (the single pipeline)

1. **Intake** → invoice lands (email/upload/API/e-invoice JSON) → duplicate check → S3 + Postgres
2. **Extraction** (async) → LLM → structured JSON → per-field confidence → template cache hit skips LLM
3. **Compliance gate** (async, parallel) → GSTN/IRP/PAN/MCA live checks + validation rules → **fail = blocked into exception queue; never reaches approval**
4. **Matching** (async) → line-level 2/3-way vs PO/GRN → auto-match or variance queue
5. **Coding & routing** → AI suggests GL/cost-center/TDS section → workflow engine routes by rules
6. **Approval** → email/web, comments on invoice, reminders, audit trail
7. **ERP posting** → connector pushes approved bill → payment status syncs back
8. **Nightly** → GSTR-2B fetch + ITC reconciliation + MSME countdown + TDS threshold checks

### Key Design Decisions

- **Tenant isolation from day one:** every table carries `tenant_id` + Postgres RLS
- **Rules as data:** validation rules, TDS rate tables, workflow rules in DB — per-tenant config, no code deploys for rule changes
- **LLM adapter pattern:** extraction behind an interface; provider swap/cost tuning without pipeline changes
- **Connector SDK:** one `ErpConnector` interface (`sync_vendors`, `sync_pos`, `sync_grns`, `push_bill`, `poll_status`)
- **E-invoice JSON as first-class input:** deterministic parse — cheaper and more accurate than competitors treating it as a PDF

---

## 5. Data Model (core entities)

```
Tenant ─┬─ User (roles: admin, ap_team, approver, viewer)
        ├─ Vendor (GSTIN, PAN, Udyam, bank, portal access)
        ├─ ErpConnection (type, credentials, mapping config)
        └─ WorkflowRule (conditions → actions)

Invoice ─┬─ Document (S3 ref, type: pdf/image/einv_json)
         ├─ ExtractedData (JSONB, per-field confidence)
         ├─ ComplianceResult (check, status, evidence, timestamp)
         ├─ MatchResult (lines, variances, tolerances applied)
         ├─ ApprovalThread (comments, attachments, decisions)
         ├─ AuditEvent (immutable, who/what/when)
         └─ ErpPostStatus (state, erp_doc_no, sync log)

Supporting: GlCode, CostCenter, TdsRateTable (versioned),
            ValidationRule, VendorTemplate (learned cache), Gstr2bRecord
```

---

## 6. Error Handling

- Every async step is **idempotent** and retried with backoff; failures land in a visible exception queue (never silent)
- Compliance gate failures block progression with a human-readable reason + evidence link
- Extraction accuracy tracked per vendor/template; corrections feed the learning loop
- External API failures (GSTN/IRP/GSP) degrade gracefully: queue-and-retry, never block intake

## 7. Testing Strategy

- Unit tests per module
- **Golden-file tests for extraction** using real Indian invoice samples (GST formats, regional languages, handwritten GRNs)
- Contract tests for GSTN/IRP/GSP clients (mocked; sandbox where available)
- E2E test of the full pipeline: intake → post
- Accuracy KPI: target ≥95% first-pass extraction on Indian B2B layouts (benchmark: OneFinOps claims 96–98%)

## 8. MVP Scope Cut

**IN:** intake (email+upload+API), LLM extraction + confidence + template cache, compliance gate (GSTIN, IRN/QR, PAN/MCA, GSTR-2B nightly, TDS engine, MSME guard, multi-GSTIN routing, ~25 extensible rules), line-level 2/3-way matching, workflow builder + email approvals + comments-on-invoice, generic ERP bridge + SAP B1 connector, basic dashboards, multi-tenant + RBAC + audit.

**OUT (v2):** WhatsApp intake/approvals, vendor portal, payments execution, advanced analytics, extra ERP connectors, SSO/SCIM, VPC packaging.

**Rationale:** MVP covers the full pipeline end-to-end with the compliance moat intact — demoable against Clear/TYASuite in a sales call. Everything deferred is additive.

## 9. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| GSP partnership/lead time for GST APIs | Start GSP evaluation immediately; MVP can ship with manual GSTR-2B CSV upload as fallback while GSP access is pending |
| LLM cost at scale | Template cache + confidence routing + provider-agnostic adapter (cheapest model per task) |
| SAP B1 connector complexity | Service Layer is well-documented; budget a dedicated milestone |
| Solo-dev bandwidth | Phased implementation plan; each module independently shippable |
| Regulatory changes (ITA 2025 renumbering, e-invoicing thresholds) | All rates/thresholds as versioned data with effective dates |

**Open questions for the dev crew to confirm during planning:**
1. Which GSP to partner with (WhiteBooks, PeriOne, IRIS, others) — evaluate API coverage, pricing, sandbox quality
2. WhatsApp Business API provider for v2 (Gupshup/Meta direct)
3. Exact SAP B1 version targets (9.x/10.x on-prem vs cloud)
