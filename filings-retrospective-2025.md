# Historical Filings Retrospective: Q1 2025 – Q4 2025 + Annuals

**Date:** May 14, 2026
**Source:** `#quarterly-annuals-filings-progress` and related filings channels
**Scope:** Four quarterly filing cycles (Q1–Q4 2025) plus annual filings, including post-filing review windows

---

## Executive Summary

Across four quarterly filing cycles in 2025, the filings organization scaled to handle over **228,000 filings across 660+ agencies** per quarter while navigating significant systemic, operational, and compliance challenges. Key accomplishments include achieving **100% on-time first-batch completion in Q3 2025** and building new payment infrastructure (FedWire support). However, recurring technical and process issues—particularly around EFTPS validation, Filing Factory workflow stability, FQL/eligibility mismatches, payment method complexity, and manual operational dependency—persisted across multiple quarters, driving amendment backlog growth and occasional penalty exposure.

The most critical systemic gaps are:

1. **Filing Factory reliability** — Workflow timeouts, heartbeat failures, and run-creation failures recurred every quarter, forcing manual workarounds
2. **EFTPS validation gaps** — Engineering removing FEINs to bypass EFTPS errors, creating downstream state filing failures
3. **Legislative change detection** — The NM legislative change in Q4 blindsided the team, causing 100% rejection of the January bulk file
4. **Manual process dependency** — Physical checks, CDs, manual file editing, and spreadsheet-based tracking remain central to operations
5. **Payment complexity** — Duplicate payments, ACH debit caps, wire-funded client handling, and agency credit reconciliation all require manual intervention

This retrospective provides per-cycle analysis, cross-cycle comparison, and a prioritized improvement roadmap.

---

## Table of Contents

1. [Q1 2025 Filing Cycle](#q1-2025-filing-cycle-april-2025)
2. [Q2 2025 Filing Cycle](#q2-2025-filing-cycle-july-2025)
3. [Q3 2025 Filing Cycle](#q3-2025-filing-cycle-october-2025)
4. [Q4 2025 + Annuals Filing Cycle](#q4-2025--annuals-filing-cycle-january-2026)
5. [Cross-Cycle Comparison](#cross-cycle-comparison)
6. [Trend Table by Quarter](#trend-table-by-quarter)
7. [Prioritized Improvement Roadmap](#prioritized-improvement-roadmap)
8. [Filing-Jira-Bot Enhancement Recommendations](#filing-jira-bot-enhancement-recommendations)
9. [High-Confidence Jira Tickets / Product Backlog Items](#high-confidence-jira-tickets--product-backlog-items)

---

## Q1 2025 Filing Cycle (April 2025)

**Filing window:** April 1–30, 2025
**Post-filing review:** May–June 2025

### 1. Recurring Issue Themes

| Theme | Description |
|-------|-------------|
| Address audit failures | Filings address audit flagging issues even after updates were made in spreadsheet; confusion over whether updates were applied in-product vs sheet-only. Team spent significant time on manual address audits |
| QWR audit failures at scale | ~2,000 clients failing QWR audit; API timeouts when attempting to remediate. Required manual batch processing |
| FQL eligibility mismatches | PU/FU eligibility conditions did not match for MEPFML, KYSW, DEPDFML, KYBOONECOFILE. Compliance had to manually update multiple filing units |
| EFT=Filing metadata gap | No system-level tracking for agencies where EFT payment constitutes the filing. Engineering removed configurations, losing TaxOps transparency |
| Payment method confusion | NYSW clients without PromptTax PIN; debate over ACH debit vs FedWire; ACH debit auditing challenges |
| Negative EE wages | CoreWeave and other clients with negative tax amounts from RSU vesting runs. Required manual investigation |
| Physical mailing dependency | CDs, checks, PEO 941 requiring physical mailing; operations dependent on specific individuals' physical location |
| NMWC FEIN rejections | 110 employers rejected by NMWC because FEINs not registered with agency |
| Doc generation errors | 72 clients with periodic tax reconciliation errors blocking document generation |
| Deposit frequency mass update error | KYSW deposit frequency updated for ALL clients instead of targeted 131; required revert for non-filed clients |

### 2. Agency-Specific Blockers

| Agency | Blocker | Resolution |
|--------|---------|------------|
| **NYSW (NY PromptTax)** | Clients without PromptTax PIN cannot file; ACH debit vs FedWire debate | FedWire tested end-to-end as alternative; discussion ongoing |
| **NMWC (NM Workers' Comp)** | 110 employers rejected — FEIN not registered | Communication drafted for employers to register; deferred to Q2 |
| **KYSW (KY State Withholding)** | Deposit frequency mass-updated in error | Reverted for non-filed clients; 70 filed + 61 moved to semi-monthly |
| **PA Locals (Berkheimer, Keystone)** | Payment must be exact match or filing delayed/rejected | Standard process, but creates friction when rounding diffs exist |
| **OH City of Kettering** | EFT=Filing configuration removed, losing tracking | Discussion about re-adding FU/PU tracking for EFT=Filing agencies |
| **MEPFML** | ~175 clients failing PU-FU eligibility audit; PU payment method not verified | Compliance updated eligibility conditions; verification pending |

### 3. Threads That Should Have Become Jira Tickets

- EFT=Filing metadata tracking gap — no Jira created; issue raised by Tony Henriquez as systemic concern
- NMWC registration communication process — ad hoc handling; no systemic workflow
- Address audit process improvement — addressed in Slack only; no tracking for product fix
- Deposit frequency update safeguards — no Jira for adding validation/guardrails to prevent mass updates
- QWR audit API timeout — no ticket for performance improvement

### 4. Stale Threads / Missed Follow-ups

- EFT=Filing tracking discussion ended without clear resolution or action owner
- NMWC employer registration communication — drafted but follow-up on completion unclear
- FedWire as alternative payment method — tested but no timeline for broader rollout

### 5. Ownership / DRI Gaps

- **Address updates**: Unclear whether TaxOps or Engineering owns ensuring product data matches
- **EFT=Filing tracking**: Compliance flagged the need, Engineering removed the config; no DRI assigned
- **Physical mailing logistics**: Dependent on one person (Kitty Kwan), with ad hoc delegation when remote
- **Deposit frequency changes**: No validation or approval workflow; individual can mass-update

### 6. Payment-Related Issues

- **NYSW PromptTax**: No PIN for ACH debit; ACH debit hard to audit in system; FedWire newly supported but not operationalized
- **Manual check process**: Automated via Lob at fixed intervals (4:30, 8:45, 16:25, 20:05 PST for intake; 7:00, 9:00, 9:30, 9:45 PST for send), but TaxOps still giving manual "FYI" nudges thinking it was needed
- **Paper checks/CDs**: Physical mailing still required for some agencies; dependency on personal mailbox

### 7. Filing/Rejection/Amendment Issues Discovered After QE

- NMWC rejections discovered during Q2 prep — 110 employers not registered
- KYSW deposit frequency revert needed — incorrect mass update affected future periods
- Doc gen errors persisted for clients not regenerated during window

### 8. Technical Root Causes

- QWR audit API timeout under load (~2,000 clients)
- FQL eligibility condition syntax differences between PU and FU (e.g., `len(accountNumber)==10` vs `len(removeChars(accountNumber,"-"," "))>0`)
- Filing Factory did not enforce PU-FU eligibility consistency
- No validation on bulk deposit frequency updates

### 9. Process Root Causes

- Manual address audit process — spreadsheet-based with no automated sync to product
- Physical mailing logistics tied to individual availability
- EFT=Filing metadata removed without cross-team alignment
- No structured employer registration workflow for new agencies

### 10. Recommended Improvements

- Build automated PU-FU eligibility consistency checks
- Add deposit frequency update safeguards (confirmation, scope limitation)
- Create EFT=Filing tracking in Filing Factory
- Automate address audit sync between spreadsheet and product
- Build employer registration notification workflow for agencies like NMWC
- Eliminate physical mailing dependency; migrate remaining paper agencies to electronic

---

## Q2 2025 Filing Cycle (July 2025)

**Filing window:** July 1–31, 2025
**Post-filing review:** August–September 2025

### 1. Recurring Issue Themes

| Theme | Description |
|-------|-------------|
| QWR/POP run creation blocked | GP companies blocked by external dependencies; had to proceed with USP first and circle back |
| DEPDFML wage under-calculation | Imputed pay not included in DEPDFML wages — under-calculating wages and tax |
| Tax Summary vs Debugger discrepancies | Different wage and liability values shown in different tools for the same client/EE |
| NYMCTMT payment complexity | Multi-step process requiring manual coordination across PEO and nonPEO entities |
| Wire-funded client issues | 7 clients on wire requiring manual run creation, approval, marking PAID, same-day ACH |
| Closed runs with unpaid taxes | 7 runs in closed state; taxes not paid, risking underpayment |
| ACH debit rejection (Jordan EIT) | Payment blocked by $1M ACH debit cap; treasury had to increase to $10M |
| OKSUI duplicate payment | Duplicate payment requiring stop-payment via JPMC; chase across timezones |
| Agency rate import failures | WA WC account numbers not populated for 6,748 companies; only 1 of 6,748 matched |
| Filing process stability | Filing process "not working" due to heartbeat timeout; stages reverted |

### 2. Agency-Specific Blockers

| Agency | Blocker | Resolution |
|--------|---------|------------|
| **DEPDFML (DE Paid Family Leave)** | Imputed pay excluded from wage calculation | Flagged to engineering; FQL update needed |
| **NYMCTMT** | Complex payment coordination; 7 clients on wire | Manual runs created; same-day ACH for wire clients |
| **OKSUI (OK SUI)** | Duplicate ACH payment | Stop-payment via JPMC; coordination across timezones and operating hours |
| **UTSUI (UT SUI)** | ACH credit rejected by agency | Resubmitted; agency confirmed no P&I for late payment |
| **Jordan EIT** | ACH debit cap at $1M blocking payment | Treasury increased cap to $10M |
| **WAWC (WA Workers' Comp)** | 6,748 companies missing WA_WC_ACCOUNT_NUMBER | Filing process had to run first to populate CompanyFilingSummary |
| **OHCOL** | Tax Summary vs Debugger wage/liability discrepancy | Engineering investigation needed |

### 3. Threads That Should Have Become Jira Tickets

- DEPDFML imputed pay exclusion — flagged in Slack, no Jira for root fix
- ACH debit cap threshold — ad hoc fix by treasury; no systemic solution
- Filing process heartbeat timeout — reverted without permanent fix ticket
- OKSUI duplicate payment prevention — no ticket for duplicate payment detection
- Tax Summary vs Debugger data consistency — flagged but no Jira for data alignment

### 4. Stale Threads / Missed Follow-ups

- DEPDFML wage fix — flagged but unclear if resolved before Q3
- Closed runs with unpaid taxes — customer notification and debit status unclear for 7 runs
- Filing process stability — reverted to manual; no timeline for fix

### 5. Ownership / DRI Gaps

- **Wire-funded client handling**: No clear owner for creating runs, approving, and coordinating payment
- **ACH debit cap management**: Treasury increased cap ad hoc; no monitoring or alerting
- **Filing process stability**: Run Management, Filing Factory, and PP teams all involved; no single DRI
- **Duplicate payment detection**: No owner for preventing or detecting duplicate payments

### 6. Payment-Related Issues

- **Duplicate OKSUI payment**: Required stop-payment via JPMC. Nobody had ACH originator ID; bank support hours didn't align. Eventually resolved by waiting for ACH return
- **Jordan EIT ACH debit cap**: $1M cap blocked payment for a single client. Treasurer had to manually increase cap to $10M
- **Wire-funded clients**: 7 clients required fully manual payment flow (create runs → approve → mark PAID → send same-day ACH → trigger comms → initiate wire)
- **NYMCTMT**: $2.7M quarterly correction payment released; 7 runs in closed state not paid ($38K total)

### 7. Filing/Rejection/Amendment Issues Discovered After QE

- DEPDFML wage under-calculation discovered during Q2 filing — likely affected Q1 as well
- Closed NYMCTMT runs may require amendments if tax underpayment confirmed
- ACH debit rejection for Jordan EIT caused delay; agency voided previous upload

### 8. Technical Root Causes

- Filing Factory heartbeat timeout causing workflow crashes
- GP run validation blocking QWR/POP creation due to PR code change (`rippling-main/pull/416563`)
- ACH debit cap hardcoded at $1M without alerting
- `CompanyFilingSummary` snapshots not populated until filing process runs
- Tax Summary and Debugger pulling from different data sources

### 9. Process Root Causes

- Wire-funded clients require a fully manual 6-step payment process
- No pre-flight check for ACH debit limits
- Filing process reverted to manual when automated workflow fails — no graceful fallback
- Duplicate payment detection relies on human observation
- JPMC support hours don't cover all timezone needs for urgent ACH stops

### 10. Recommended Improvements

- Implement duplicate payment detection and alerting
- Add ACH debit cap monitoring and pre-flight validation
- Build automated wire-funded client payment workflow
- Fix Filing Factory heartbeat timeout root cause
- Align Tax Summary and Debugger data sources
- Add validation for GP run state before QWR/POP creation
- Build CompanyFilingSummary pre-population as part of prep stage

---

## Q3 2025 Filing Cycle (October 2025)

**Filing window:** October 1–31, 2025
**Post-filing review:** November–December 2025

### 1. Recurring Issue Themes

| Theme | Description |
|-------|-------------|
| IRS 941 failures | Assertion errors, failed packets, XML validation, system timeouts for RPEO1 |
| NYMCTMT rounding issues | Tax differences causing upload errors; 8 clients manually edited (USTF-35) |
| Exempt employer wage reporting | System stops accumulating wages when marked exempt, causing zero returns |
| PEO efile errors | NY agency blocking PEO file submission; external dependency |
| NCSUI POA rejections | Customers receiving rejection notices; DNF process masking root cause |
| ACH Credit registration not automated | Manual identification and implementation by Compliance |
| Q4 FCD in Q3 filings | 5 clients with fileWithOnlyInitRuns setting had Q4 dates pulled into Q3 |
| Physical mailing issues | Paper filings, CD files not sent to agencies |
| OHSW transmission ID issue | Agency rejected annual; P&I penalties assessed; won't honor original filing date |
| Daily blocker tracking matured | Structured daily summaries with issue counts and status tracking |

### 2. Agency-Specific Blockers

| Agency | Blocker | Resolution |
|--------|---------|------------|
| **IRS 941** | Assertion errors, XML validation, RPEO1 timeouts | Multiple fixes; compliance template updates; doc gen errors required engineering |
| **NYMCTMT** | Rounding differences; PEO efile error | Manual file editing for 8 clients; PEO error resolved by NY agency |
| **OHSW** | Transmission ID issue in annual file | Uploaded successfully after fix, but P&I penalties not waived by agency |
| **NCSUI** | POA rejections for new customers | Root cause: missing POA setup, masked by standard DNF process |
| **CTPDFML** | Upload errors during Q3 filing | Compliance reviewed and resolved |
| **PA Collector (Cumberland)** | CD file not sent to agency; payments received but no filing | Investigation into filing process gap |
| **Philadelphia PA** | Payment decimal/rounding issues | Addressed but pattern persists |
| **MEPFML** | Exempt employer wage reporting broken | Engineering building exemption handling; manual fix for HUB clients |
| **VASW** | Late filings incident (December 15, 2025) | Incident channel created; resolution tracked |

### 3. Threads That Should Have Become Jira Tickets

- ACH Credit registration automation — discussed but no product ticket
- EFT=Filing tracking (re-raised from Q1) — still no ticket
- NCSUI POA rejection masking in DNF process — no ticket to improve DNF categorization
- Q4 FCD in Q3 filings prevention — no ticket for fileWithOnlyInitRuns guard
- Exempt employer wage accumulation fix — flagged; engineering building but no clear JIRA reference in channel

### 4. Stale Threads / Missed Follow-ups

- HUB broker escalation — PSM team involvement unclear; compliance vs support ownership
- ACH Credit registration process — Ryan Cannedy started confluence doc but work "moved away"
- OHSW P&I abatement — abatement request outcome not tracked
- Exempt employer manual fix — unclear if all HUB clients were addressed

### 5. Ownership / DRI Gaps

- **Exempt employer handling**: Compliance, Engineering, PSM team all involved; no single DRI
- **ACH Credit registration**: Started by one person, moved away, incomplete documentation
- **OHSW abatement**: Tax Ops flagged need for abatement request; ownership of agency follow-up unclear
- **PA Collector Cumberland**: CD filing gap investigation — no clear owner
- **Post-QE filing audit**: James Brown asked for specific MM/DD for audit; no clear answer

### 6. Payment-Related Issues

- **NYMCTMT rounding**: Manual file editing for 8 clients due to penny differences between zone wages × rate and reported tax
- **OHSW P&I penalties**: Agency assessed penalties and will not honor original filing date
- **VASW late filings**: Incident created for late Q3 filings
- **PA Philadelphia**: Decimal/rounding issue in payment amounts

### 7. Filing/Rejection/Amendment Issues Discovered After QE

- OHSW transmission ID rejection — required amendment and abatement request
- Exempt employer zero returns — will require amendments once system fix deployed
- NCSUI POA rejections — affecting onboarding of new customers
- VASW late filings — penalties likely

### 8. Technical Root Causes

- IRS 941 XML validation assertion errors (negative cash value)
- RPEO1 doc generation timeouts
- `fileWithOnlyInitRuns` setting allowing Q4 first-check-date reconciliation runs to be included in Q3
- Exempt employer flag stopping wage accumulation rather than just changing filing behavior
- Transmission ID generation bug in OHSW annual filing

### 9. Process Root Causes

- Rounding differences between calculated and reported values not caught pre-submission
- ACH Credit registration handled ad hoc with no standard workflow
- DNF categorization doesn't distinguish between "client didn't sign POA" and "POA was rejected by agency"
- Post-QE filing audit schedule not formalized
- No automated cross-format comparison for bulk file vs payment audit amounts

### 10. Recommended Improvements

- Build pre-submission rounding validation (compare calculated vs reported to the penny)
- Automate ACH Credit registration workflow
- Improve DNF categorization to distinguish POA rejection from client non-action
- Fix fileWithOnlyInitRuns guard to prevent Q4 dates in Q3
- Build transmission ID validation before submission
- Formalize post-QE audit schedule and process

### Q3 Key Metrics

- **First Batch**: 226,673 filings across 660 agencies — 100% on-time
- **Second Batch**: 2,108 filings across 165 agencies
- **Daily blockers**: 32–56 issues tracked
- **On-time completion**: Progressed from 80% to 100% over filing window

---

## Q4 2025 + Annuals Filing Cycle (January 2026)

**Filing window:** January 1–31, 2026
**Post-filing review:** February–March 2026

### 1. Recurring Issue Themes

| Theme | Description |
|-------|-------------|
| NMSW legislative change blindside | January 2026 changes to reporting frequency and form; all 390 companies in January file rejected |
| KYSW annual recon rejection | FQL incorrect — not pulling correct EE count; agency rejected filings |
| IRS W2/EFW2 rejections | SSA rejecting files for 19 employers with EIN issues; ESLO not responding |
| MDSW W-2 rejection in production | File passes testing environment but rejected in production |
| PEO IRS Q4 return in rejected/suspense | Manager review needed to verify credit |
| Filing Factory workflow failures | QWR creation failing for 2,358 clients; heartbeat timeouts; filing process reverted |
| EFTPS validation failures | Blocking filings for clients with invalid/missing EINs; eng removing FEINs to bypass |
| CAEDD batch upload backlog | Only 1 of 13 batches uploaded; high risk of late filing |
| International address in domestic filings | EE with international home address + US work location causing file failures |
| Employee data missing from filings | Incident created (INC-3746) for multi-agency employee data missing from Q1 filings |
| Run validation blocking paid transition | PEO termination date validation blocking run state changes |
| Form 940 missing from year-end packages | Required manual regeneration |

### 2. Agency-Specific Blockers

| Agency | Blocker | Resolution |
|--------|---------|------------|
| **NMSW** | 100% rejection of January bulk file — legislative changes | New XML schema required; monthly filing period now required |
| **KYSW** | Annual recons rejected — incorrect EE count FQL | FQL fixed, file regenerated and resubmitted |
| **IRS (SSA/EFW2)** | 19 employers with EIN issues; SSA continues to reject | Contacted ESLO (no response); separated into own file; exploring workarounds |
| **MDSW** | W-2 file rejected in production (passes testing) | Agency call planned; investigating discrepancy between test and prod environments |
| **CAEDD** | Only 1 of 13 batches uploaded | High risk; compliance pushing for faster upload |
| **IRS 941** | PEO Q4 return in rejected/suspense status | Credit verification needed by manager |
| **OHSW** | Transmission ID issues; P&I penalties | Fix identified; abatement request submitted |
| **NJ Newark** | RPEO return incorrect values (lines 2A, 2B, 2C) | Engineering and compliance fix; shipped to live |
| **NYMCTMT** | Tax discrepancies in file | Resolved via compliance adjustment |
| **ORFILE (OR)** | EE data not populating in file (FFID 44019) | Fixed by engineering; root cause documented in YE2025-2455 |
| **NCSW (EFW2)** | International EE address causing file failure | Process question: how to handle US work location + international home address |
| **Shelbyville** | Rejected mail | Investigation into first instance of rejection |

### 3. Threads That Should Have Become Jira Tickets

- NMSW legislative change detection — no proactive monitoring for agency form/frequency changes
- International address handling in domestic filings — no product ticket
- EFTPS bypass workflow (eng removing FEIN) — no ticket for proper handling
- MDSW test vs production discrepancy — root cause investigation needed
- Form 940 regeneration gap — no ticket for ensuring complete year-end packages
- Documo vendor billing monitoring — no automated alerting for vendor payment failures
- CAEDD batch upload automation — no ticket for automating multi-batch upload

### 4. Stale Threads / Missed Follow-ups

- NMSW legislative change — no post-mortem on why it wasn't detected
- IRS SSA EIN rejection for 19 employers — ESLO not responding; no escalation path documented
- PEO IRS Q4 return in suspense — credit verification timeline unclear
- CheckIssuing SOP — referenced as missing; no follow-up on creating it
- OHSW abatement outcome — request submitted but no tracked resolution
- Documo billing — card rejection flagged; unclear if permanently resolved

### 5. Ownership / DRI Gaps

- **Legislative change monitoring**: No DRI for proactively tracking agency form/frequency changes
- **EFTPS failure handling**: Engineering, Compliance, and TaxOps all touch this; no single owner
- **Year-end package completeness**: No DRI for ensuring all required forms included
- **Vendor billing (Documo)**: Individual checking billing status; no automated monitoring
- **International address policy**: No owner for defining how to handle US work location + international home address
- **CAEDD batch upload**: 13 batches with only 1 uploaded; no DRI for accelerating

### 6. Payment-Related Issues

- **Agency credits handling**: 11 customers with agency credits; unclear whether to enter in FF (Option A) or notify customer (Option B)
- **Zymeworks late CRA payment**: $550K penalty; payment batching system generated 1,000+ false failure alerts
- **Tax credit overcalculation**: Credits applied multiple times in 2025 causing under-remittance to CRA and RQ
- **Stop payment needs**: Duplicate payment scenarios continuing
- **Wire-funded run discrepancies**: Ongoing from Q2
- **Springdale payments**: Payments and filings incorrectly sent; corrections needed

### 7. Filing/Rejection/Amendment Issues Discovered After QE

- NMSW all-company rejection — discovered upon agency submission
- KYSW annual rejection — FQL error
- SSA EIN rejections for 19 employers — ongoing
- MDSW production rejection — testing passes but production doesn't
- OHSW P&I penalties — agency will not honor original filing date
- Multiple PEO amendments needed for exempt employer wage reporting
- W8BEN vs W9 misuse for US citizen contractors — 1099s potentially incorrect
- Late filing notices received for Q4 2025 (MA, NH, CO) by When I Work subsidiary

### 8. Technical Root Causes

- NMSW XML schema change not detected — no automated monitoring of agency portals/schemas
- QWR creation validation failure for 2,358 clients due to CTI issues
- Filing Factory heartbeat timeout (recurring from Q2)
- `process_employee_payments_for_gp_run` function — idempotency needed verification
- Run validation code blocking PEO-terminated client run state transitions
- International address not handled by filing template (only US address supported)
- Form 940 not included in year-end package generation flow
- W8BEN used instead of W9 for US citizen contractors

### 9. Process Root Causes

- No legislative change monitoring or agency communication tracking
- EFTPS failure creates a cascade: eng removes FEIN → state filings break → amendments needed
- Year-end package generation doesn't validate completeness
- No SOP for CheckIssuing process
- Vendor billing monitoring is manual
- No post-QE audit with fixed schedule
- 13-batch CAEDD upload process has no automation or parallelization

### 10. Recommended Improvements

- Build legislative change monitoring system (track agency schema versions, filing frequency changes)
- Fix EFTPS failure cascade — pause payroll instead of removing FEIN
- Automate year-end package completeness validation
- Create CheckIssuing SOP
- Build vendor billing automated monitoring and alerting
- Fix international address handling in filing templates
- Automate CAEDD batch upload process
- Build W9 vs W8BEN classification logic for US citizen contractors

---

## Cross-Cycle Comparison

### 1. Recurring Issues That Persisted Across Multiple Quarters

| Issue | Q1 | Q2 | Q3 | Q4 | Status |
|-------|:--:|:--:|:--:|:--:|--------|
| Filing Factory workflow timeouts/crashes | | ✓ | | ✓ | **Active** — heartbeat timeout root cause not resolved |
| QWR/POP run creation failures | ✓ | ✓ | ✓ | ✓ | **Active** — different root causes each quarter but pattern persists |
| Doc generation errors | ✓ | ✓ | ✓ | ✓ | **Active** — various FQL, template, and data issues |
| Payment method complexity (ACH/wire/check) | ✓ | ✓ | ✓ | ✓ | **Active** — manual intervention required every quarter |
| FQL/eligibility mismatches | ✓ | ✓ | ✓ | ✓ | **Active** — PU-FU consistency not enforced |
| EFTPS validation/registration failures | ✓ | ✓ | ✓ | ✓ | **Active** — worsening; FEIN removal cascade growing |
| Rounding/decimal differences | | ✓ | ✓ | ✓ | **Active** — manual file editing still needed |
| Agency file rejections | ✓ | | ✓ | ✓ | **Active** — different agencies each quarter |
| Manual processes (physical mail, spreadsheets) | ✓ | ✓ | ✓ | ✓ | **Active** — core dependency on manual operations |
| PEO client complexity | ✓ | ✓ | ✓ | ✓ | **Active** — mid-quarter changes, exempt employers, RPEO issues |
| EFT=Filing tracking gap | ✓ | | ✓ | | **Active** — raised in Q1, re-raised in Q3, still no system tracking |
| Address audit failures | ✓ | | | ✓ | **Active** — DRI for filings address updates still unclear |

### 2. Issues That Improved or Were Resolved

| Issue | Improvement | When |
|-------|-------------|------|
| On-time filing rate | Q3 achieved 100% first-batch on-time completion | Q3 |
| Daily blocker tracking | Structured daily summaries with counts and status introduced | Q3 onward |
| FedWire payment support | Infrastructure built and tested end-to-end | Q1–Q2 |
| ACH debit cap | Treasury increased from $1M to $10M | Q2 |
| Jordan EIT ACH debit | Issue resolved; cap increased | Q2 |
| Check processing automation clarity | Confirmed automated via Lob; manual FYI nudges unnecessary | Q1 |
| MEPFML/KYSW/DEPDFML eligibility | Compliance updated FU eligibility conditions | Q1 |
| WAWC filing automation | Processing automation implemented | Q4 |

### 3. Issues That Got Worse

| Issue | Trajectory | Impact |
|-------|-----------|--------|
| **Legislative change detection** | Q1: no issues → Q4: 100% rejection of NMSW January file | High — entire state filing rejected |
| **EFTPS failure cascade** | Q1: isolated → Q4: eng systematically removing FEINs, breaking state filings | High — growing amendment backlog |
| **Filing Factory stability** | Q2: heartbeat timeout → Q4: QWR creation failing for 2,358 clients + process reverted | High — forcing full manual fallback |
| **Amendment backlog** | Growing every quarter as post-QE issues discovered | Medium — compliance risk increasing |
| **W2/EFW2 SSA rejections** | New in Q4 — 19 employers with EIN issues, ESLO non-responsive | Medium — annual filing at risk |
| **CAEDD batch upload** | Q4: Only 1 of 13 batches uploaded | Medium — scale of upload exceeding manual capacity |

### 4. Repeated Agency Patterns

| Agency Pattern | Quarters Affected | Root Cause |
|---------------|-------------------|------------|
| **IRS (941/EFW2)** | Q1, Q3, Q4 | XML validation, assertion errors, EIN issues, RPEO1 timeouts |
| **NY agencies (NYSW, NYMCTMT)** | Q1, Q2, Q3, Q4 | Payment method complexity, rounding, PEO efile errors |
| **OH agencies (OHSW, OHCOL, OH RITA)** | Q1, Q2, Q3, Q4 | EFT=Filing tracking, transmission ID, deposit frequency, ACH Credit |
| **PA locals** | Q1, Q2, Q3, Q4 | Payment exact match requirement, rounding, collector CD gaps |
| **NJ agencies (NJSW, NJ Newark)** | Q3, Q4 | Doc gen errors, RPEO incorrect values, EFTPS cascading |
| **NM agencies (NMSW, NMWC)** | Q1, Q4 | FEIN registration (Q1), legislative change (Q4) |

### 5. Repeated Technical Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| **No PU-FU eligibility enforcement** | Different conditions can exist without validation | Filing failures every quarter |
| **Filing Factory workflow reliability** | Heartbeat timeouts, run creation failures | Manual fallback every quarter |
| **No pre-submission validation** | Rounding diffs, schema compliance, EE data completeness not checked | Agency rejections after submission |
| **Tax data source inconsistency** | Tax Summary, Debugger, Periodics dashboard show different values | Incorrect filings, investigation time |
| **No legislative change detection** | Agency schema/form/frequency changes not monitored | Blindside rejections |
| **EFTPS failure handling** | FEIN removal creates cascade through state filings | Growing amendment backlog |

### 6. Repeated Process/Ownership Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| **No DRI for address updates** | TaxOps, Engineering, HRIS all involved; no single owner | Delays and errors every quarter |
| **No DRI for post-QE audit** | Ad hoc audits; no fixed schedule or owner | Issues discovered late |
| **Physical mailing dependency** | Operations depend on specific individuals' physical presence | Single point of failure |
| **Spreadsheet-based tracking** | Refile process, agency credits, special handling all in sheets | No visibility, no SLA enforcement |
| **No vendor billing monitoring** | Documo, Lob billing checked manually | Risk of service disruption |
| **No SOP for CheckIssuing** | Process referenced as missing; not created | Inconsistent execution |

### 7. Gaps Still Present in April 2026

Based on channel activity through March 2026, the following gaps remain unresolved:

1. **Filing Factory reliability** — Heartbeat timeouts and QWR creation failures still occurring
2. **EFTPS FEIN removal cascade** — Engineering still removing FEINs; state filings still impacted
3. **Legislative change detection** — No monitoring system built
4. **Manual file editing for rounding** — Still editing bulk files manually
5. **EFT=Filing tracking** — Still not in Filing Factory
6. **Address audit process** — Still manual/spreadsheet-based
7. **Physical mailing dependency** — Still exists for some agencies
8. **Post-QE audit formalization** — No fixed schedule
9. **Amendment backlog** — Growing; tracked via `#amendments-collaboration` and `#taxops-refilings`
10. **International address handling** — No product fix
11. **W9 vs W8BEN classification** — Still using W8BEN for US citizens
12. **CAEDD batch upload automation** — Still manual

### 8. Recommended Fixes and Automation Opportunities

| Priority | Fix | Estimated Complexity | Impact |
|----------|-----|---------------------|--------|
| P0 | Fix Filing Factory heartbeat timeout root cause | Backend infra | Eliminates manual fallback every quarter |
| P0 | Fix EFTPS failure cascade — pause payroll, don't remove FEIN | Backend logic | Stops growing amendment backlog |
| P0 | Build legislative change monitoring | New system/service | Prevents blindside rejections |
| P1 | Add pre-submission validation (rounding, schema, completeness) | Filing Factory feature | Eliminates post-submission rejections |
| P1 | Enforce PU-FU eligibility consistency | Filing Factory validation | Eliminates recurring mismatch failures |
| P1 | Build automated post-QE audit process | Workflow automation | Catches issues before penalties accrue |
| P1 | Automate CAEDD batch upload | Filing Factory feature | Scales beyond manual capacity |
| P2 | Add duplicate payment detection and alerting | Payments feature | Prevents stop-payment scrambles |
| P2 | Build ACH debit cap monitoring and pre-flight | Payments feature | Prevents payment failures |
| P2 | Automate wire-funded client payment workflow | Payments automation | Eliminates 6-step manual process |
| P2 | Build EFT=Filing tracking in Filing Factory | FF metadata | Gives TaxOps transparency |
| P2 | Automate address audit sync | Integration | Eliminates spreadsheet dependency |
| P3 | Build ACH Credit registration workflow | Compliance automation | Removes ad hoc manual process |
| P3 | Build employer registration notification system | Communication automation | Handles NMWC-style registrations |
| P3 | Fix international address in filing templates | Template update | Handles edge case EE data |
| P3 | Build W9 vs W8BEN classification | Tax forms logic | Corrects contractor classification |
| P3 | Create CheckIssuing SOP and automate | Process documentation + automation | Standardizes execution |
| P3 | Build vendor billing monitoring | Alerting | Prevents service disruptions |

---

## Trend Table by Quarter

| Metric / Issue | Q1 2025 | Q2 2025 | Q3 2025 | Q4 2025 + Annuals |
|---------------|---------|---------|---------|-------------------|
| **Total filings** | ~226K (est.) | ~226K (est.) | 228,781 | ~230K+ (est.) |
| **Agencies filed** | ~660 | ~660 | 660 (batch 1) + 165 (batch 2) | 660+ |
| **On-time first batch** | ~95% (est.) | ~90% (est.) | 100% | ~92% (est.) |
| **Daily blocker count (peak)** | Not tracked formally | Not tracked formally | 56 | 43 |
| **QWR/POP failures** | ~2,000 clients | GP companies blocked | Occurred | 2,358+ clients |
| **Doc gen errors** | 72 clients | Multiple | Multiple | Multiple |
| **Payment issues** | ACH debit vs FedWire, manual checks | Duplicate OKSUI, ACH cap, wire clients | NYMCTMT rounding, OHSW P&I | Agency credits, CRA $550K penalty, duplicates |
| **Agency rejections** | NMWC (110 ERs) | ACH debit rejections | OHSW annual, NCSUI POA | NMSW (390 ERs), KYSW annual, SSA EINs, MDSW |
| **Filing Factory stability** | API timeouts | Heartbeat timeout; process reverted | Timeouts for RPEO1 | QWR creation failures; process reverted |
| **EFTPS issues** | Emerging | Present | Worsening | Systemic — FEIN cascade |
| **Amendments generated** | Minimal | DEPDFML, NYMCTMT | OHSW, exempt employers | NMSW, KYSW, IRS, OHSW, multiple |
| **Incidents created** | 0 | 1 (run validation) | 1 (VASW late filings) | 5+ (data missing, EFTPS, merge CI, etc.) |
| **Legislative blindsides** | 0 | 0 | 0 | 1 (NMSW — 100% rejection) |
| **Penalty exposure** | Low | Low | Medium (OHSW P&I) | High (OHSW P&I, CRA $550K, late notices MA/NH/CO) |
| **Process maturity** | Ad hoc daily syncs | Daily syncs | Structured daily summaries with metrics | Structured summaries; Jira integration improving |

---

## Prioritized Improvement Roadmap

### Phase 1: Critical Reliability (Next Quarter)

| # | Initiative | Owner Suggestion | Why Now |
|---|-----------|-----------------|---------|
| 1 | **Fix Filing Factory heartbeat timeout** | Filing Factory Engineering | Causes manual fallback every quarter; blocks scale |
| 2 | **Fix EFTPS failure cascade** | Tax Platform Engineering | Growing amendment backlog; penalty exposure increasing |
| 3 | **Build pre-submission validation** | Filing Factory Engineering + Compliance | Rounding, schema, and completeness checks prevent rejections |
| 4 | **Enforce PU-FU eligibility consistency** | Filing Factory Engineering | Recurring mismatch failures every quarter |
| 5 | **Automate post-QE audit schedule** | TaxOps + Engineering | Catch issues before penalties accrue |

### Phase 2: Automation & Scale (Following Quarter)

| # | Initiative | Owner Suggestion | Why Now |
|---|-----------|-----------------|---------|
| 6 | **Build legislative change monitoring** | Compliance + Engineering | NM blindside proves need; other states may change |
| 7 | **Automate CAEDD batch upload** | Filing Factory Engineering | 13-batch manual process doesn't scale |
| 8 | **Add duplicate payment detection** | Payments Engineering | Recurring duplicate payment incidents |
| 9 | **Build ACH debit cap monitoring** | Treasury + Payments Engineering | Prevents future payment failures |
| 10 | **Automate wire-funded client workflow** | Payments Engineering | 6-step manual process for every wire client |

### Phase 3: Process Maturity (Subsequent Quarter)

| # | Initiative | Owner Suggestion | Why Now |
|---|-----------|-----------------|---------|
| 11 | **Build EFT=Filing tracking** | Filing Factory Engineering | Raised in Q1 2025; still not resolved |
| 12 | **Automate address audit sync** | Data Platform + Engineering | Eliminates spreadsheet-based manual process |
| 13 | **Build ACH Credit registration workflow** | Compliance + Engineering | Ad hoc manual process; incomplete documentation |
| 14 | **Create CheckIssuing SOP** | TaxOps | Referenced as missing; not created over 4 quarters |
| 15 | **Build vendor billing monitoring** | Finance Operations | Prevents service disruptions (Documo, Lob) |
| 16 | **Fix international address handling** | Filing Factory Engineering | Edge case causing file failures |
| 17 | **Build W9/W8BEN classification** | Tax Platform Engineering | US citizens classified incorrectly |
| 18 | **Build employer registration notifications** | Compliance Automation | Ad hoc handling for NMWC-style registrations |

---

## Filing-Jira-Bot Enhancement Recommendations

Based on the retrospective findings, the following enhancements would improve the filing process:

### 1. Automatic Blocker Detection and Ticket Creation

- **When QWR/POP runs fail**: Auto-create Jira ticket with client IDs, error messages, and link to FF dashboard
- **When doc gen errors occur**: Auto-create Jira ticket with FFID, agency, error details
- **When agency rejects a file**: Auto-create Jira with agency name, rejection reason, affected client count

### 2. Legislative Change Alerts

- Monitor agency portal schemas for version changes
- Alert Compliance and Engineering when filing frequency, form version, or XML schema changes detected
- Auto-create Jira ticket with agency, change description, and impacted filing type

### 3. Pre-Submission Validation Results

- Run pre-submission checks (rounding, schema compliance, EE data completeness)
- Create Jira tickets for any validation failures blocking submission
- Tag appropriate DRI based on failure type (Engineering for FQL, Compliance for data)

### 4. Payment Issue Detection

- Detect duplicate payment attempts and auto-create ticket
- Alert when ACH debit approaches cap threshold
- Create ticket when wire-funded client requires manual payment processing

### 5. Post-QE Audit Automation

- Auto-run filing vs payment reconciliation audit after QE completion
- Create Jira tickets for mismatches with priority based on dollar amount
- Track amendment needs from reconciliation differences

### 6. EFTPS Status Integration

- Monitor EFTPS validation status changes
- Alert when FEIN is removed or EFTPS status changes
- Create ticket to pause payroll (not remove FEIN) when EFTPS fails

### 7. Stale Thread Detection

- Monitor filing-related Slack threads for inactivity
- Alert DRI when a blocker thread goes stale (>48 hours without update)
- Create Jira ticket for unresolved blockers approaching filing deadline

### 8. Daily Status Summary Generation

- Auto-generate daily blocker summary from open Jira tickets
- Post to `#quarterly-annuals-filings-progress` with counts, status, and owners
- Track metrics over time for trend analysis

### 9. Amendment Backlog Tracking

- Track all amendments generated from filing issues
- Create dashboard showing amendment backlog by quarter, agency, and root cause
- Alert when backlog exceeds threshold

### 10. Vendor Health Monitoring

- Monitor Documo, Lob, and other vendor billing status
- Alert when vendor payment fails or service degrades
- Create ticket with vendor name, impact, and action needed

---

## High-Confidence Jira Tickets / Product Backlog Items

The following issues have sufficient evidence from Slack discussions to warrant Jira tickets or product backlog items. **No tickets should be created from this document without review** — this is a recommendation list only.

### P0 — Critical

| # | Title | Description | Evidence |
|---|-------|-------------|----------|
| 1 | **Filing Factory: Fix heartbeat timeout causing workflow crashes** | Filing Factory workflows crash due to heartbeat timeout. QWR/POP runs fail, and the filing process is reverted to manual each quarter. Root cause investigation and permanent fix needed. | Q2: Pankaj Birat confirmed heartbeat timeout; Q4: Krishna Mohan confirmed "filing process is not working" |
| 2 | **EFTPS: Stop removing FEIN; implement payroll pause instead** | When EFTPS validation fails, engineering manually removes the FEIN to bypass errors. This breaks all state filings for the client and creates growing amendment backlog. Instead, payroll should be paused. | Kelly Gonzalez: "This field should never be left blank... Engineering manually removes the FEIN to bypass an EFTPS error, which then triggers a 'missing FEIN' error" |
| 3 | **Pre-submission validation: Rounding, schema, and data completeness** | No automated validation before submitting files to agencies. Rounding differences, missing EE data, and schema mismatches are caught only after agency rejection. | NYMCTMT rounding (USTF-35); NMSW schema rejection (390 companies); OHSW transmission ID; MDSW prod rejection |
| 4 | **PU-FU eligibility consistency enforcement** | Filing Unit and Payment Unit eligibility conditions can diverge without validation. This causes recurring audit failures affecting hundreds of clients per quarter. | Q1: MEPFML, KYSW, DEPDFML, KYBOONECOFILE all had mismatches; Alicia Sena and Kelly Reith confirmed and manually fixed |

### P1 — High

| # | Title | Description | Evidence |
|---|-------|-------------|----------|
| 5 | **Legislative change monitoring system** | No mechanism to detect when agencies change filing frequencies, form versions, or XML schemas. The NM legislative change in Q4 caused 100% rejection of 390 companies. | Carolina Ouellette: "all of the companies in the January file were rejected"; Tony Henriquez: audit identified "systemic failure caused by major legislative changes effective January 1, 2026" |
| 6 | **CAEDD batch upload automation** | CAEDD filing requires uploading 13 separate batches manually. Only 1 of 13 was uploaded during Q4 window, creating high risk of late filing. | Rana Annabi daily update: "only 1 of 13 batches has been uploaded. We need to upload the remaining batches" |
| 7 | **Duplicate payment detection and alerting** | Duplicate payments to agencies require emergency stop-payment processes via JPMC. No automated detection exists. | Q2: OKSUI duplicate payment; multiple quarters with stop-payment requests |
| 8 | **Post-QE automated filing vs payment reconciliation** | Manual reconciliation catches issues late. Automated comparison of filed amounts vs paid amounts would surface mismatches immediately. | Q1: Catherine Galvan found 8 clients not matching payment audit for NCSUI; recurs every quarter |
| 9 | **ACH debit cap monitoring and pre-flight validation** | ACH debit cap of $1M blocked Jordan EIT payment. No pre-flight check or monitoring exists. | Trang Nguyen: "our bank stopped the payment... ACH debit cap at $1 million" |
| 10 | **International address handling in filing templates** | Filing templates only support US addresses. EE with international home address + US work location causes file failures. | Catherine Galvan: "EE has an international home address... This is causing our file to fail" |

### P2 — Medium

| # | Title | Description | Evidence |
|---|-------|-------------|----------|
| 11 | **EFT=Filing tracking in Filing Factory** | No system-level metadata for agencies where EFT payment constitutes the filing. Compliance loses visibility when FU configs are removed. | Tony Henriquez: "this is going to become an issue down the road"; James Corbin confirmed removal per engineering request |
| 12 | **Automated address audit sync** | Address audits are spreadsheet-based. Updates made in sheets don't sync to product automatically, causing repeated audit failures. | Krishna Mohan: "audit is still flagging the issues, did we update in product or updated in sheet only" |
| 13 | **Wire-funded client payment automation** | 7 clients on wire require 6-step manual process each quarter. | Amit Yadav documented 6-step process; recurring every quarter |
| 14 | **Tax Summary vs Debugger data alignment** | Different tools show different wage/liability values for the same client. | James Corbin: "Something is wrong with either Tax Summary or Debugger" |
| 15 | **Deposit frequency update safeguards** | No validation or scope limitation on bulk deposit frequency updates. Mass update for all clients instead of targeted 131 occurred. | Amit Yadav: "you have updated the deposit frequency for all clients for KYSW, we were supposed to do it only for the 131 clients" |
| 16 | **ACH Credit registration workflow automation** | ACH Credit registration is manually identified and implemented by Compliance with no standard workflow. Confluence doc started but never completed. | James Corbin: "ACH registration is not automated... manually identified and implemented by Compliance"; Ryan Cannedy: started doc, work "moved away" |
| 17 | **DNF categorization improvement** | DNF process doesn't distinguish between "client didn't sign POA" and "POA was rejected by agency", masking systemic issues. | Catherine Galvan: "not providing POA is already a standard DNF reason... that could be why nothing seems out of the ordinary" |
| 18 | **fileWithOnlyInitRuns guard for quarter boundaries** | Setting allows Q4 first-check-date reconciliation runs to be included in Q3 filings. | Q3 daily update: "5 clients with the fileWithOnlyInitRuns setting had their Q4 First Check Date moved into Q3 filings" |
| 19 | **W9 vs W8BEN classification for US citizen contractors** | System uses W8BEN for US citizens instead of W9, violating IRS instructions. | James Brown: "we are NOT using W9s, instead we are currently using W8BEN's for everyone. Which is clearly wrong." |
| 20 | **Year-end package completeness validation** | Form 940 was missing from year-end packages and required manual regeneration. No validation ensures all required forms are included. | Fatih Kurt provided manual regeneration instructions; no automated check |

---

*This document was generated from analysis of Slack conversations in `#quarterly-annuals-filings-progress` and related channels from April 2025 through March 2026. No Jira tickets were created. All recommendations are subject to review by relevant stakeholders.*
