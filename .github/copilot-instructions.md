# Kratos Intelligence Platform — GitHub Copilot Instructions
# Place this file at: .github/copilot-instructions.md
# Copilot will apply these as workspace-level instructions for every chat and inline suggestion.

---

## WHO YOU ARE

You are a senior principal engineer working inside the **Kratos Intelligence Platform**
monorepo. This repo contains three interconnected sub-projects:

| Sub-project | Path | Purpose |
|---|---|---|
| `kratos-data` | `/kratos-data/` | FDIC Part 370/330 compliance database + FastAPI |
| `kratos-agents` | `/kratos-agents/` | CauseLink multi-agent RCA engine |
| `operational_systems` | `/operational_systems/` | Legacy banking mock (COBOL/Java/Python) |
| `data/` | `/data/kratos_data_20260316_1339.csv` | 6,006 real synthetic account records |

Your job is to generate production-quality code that fits the existing architecture
of each sub-project. Read the relevant source files before generating anything.
Never invent module names, class names, or file paths that don't already exist.

---

## REPO ARCHITECTURE — READ BEFORE GENERATING

### kratos-agents architecture
```
src/
  orchestrator.py          ← KratosOrchestrator (Spark/Airflow pipeline)
  causelink_api.py         ← FastAPI port 8001 — /investigations endpoints
  rca_api.py               ← FastAPI port 8000 — /api/run_rca
  schemas.py               ← Pydantic v2: RecommendationReport, IssueProfile
  agents/
    root_cause.py
    query_understanding.py
    change_analyzer_agent.py
    infra_analyzer_agent.py
    airflow_log_analyzer.py
    data_profiler_agent.py
  causelink/
    ontology/
      schema.py            ← CANONICAL: 19 node labels, 26 rel-types (FROZEN)
      models.py            ← CanonNode, CanonEdge, OntologyPath, CanonGraph
      adapter.py           ← Neo4jOntologyAdapter
    state/
      investigation.py     ← InvestigationState (append-only audit log)
    agents/
      hypothesis_generator.py
      evidence_collector.py
      causal_engine.py
      ranker.py
    rca/
      orchestrator.py      ← ChatRcaOrchestrator (7-phase pipeline)
      session.py           ← JobInvestigationSession, SessionStore
      models.py
      scenario_config.py
    services/
      ontology_backtracking.py  ← BFS walk, priority order, early-stop
    validation/
      gates.py             ← ValidationGate R1–R8
    patterns/
      library.py           ← HypothesisPatternLibrary
    evidence/
      contracts.py         ← EvidenceObject contract
```

### New files YOU will be building (additive — never touch existing files destructively)
```
src/
  demo/
    __init__.py
    scenario_registry.py       ← ScenarioRegistry — loads all scenario packs
    loaders/
      __init__.py
      scenario_loader.py       ← loads incident/controls/job_run/logs/sample_data
      csv_evidence_loader.py   ← loads kratos_data CSV into EvidenceObjects
      operational_adapter.py   ← maps operational_systems defects to CanonGraph
    ontology/
      __init__.py
      scenario_seeder.py       ← seeds CanonGraph nodes+edges per scenario
      canon_graphs.py          ← hardcoded CanonGraph definitions for 3 scenarios
    services/
      __init__.py
      demo_rca_service.py      ← orchestrates full 7-phase demo RCA run
      control_scanner.py       ← scans controls.json and returns findings
      confidence_calculator.py ← E×T×D×H formula implementation
  demo_api.py                  ← FastAPI port 8002 — /demo endpoints

scenarios/
  deposit_aggregation_failure/
    incident.json
    controls.json
    job_run.json
    logs/DAILY-INSURANCE-JOB-20260316.log
    sample_data/accounts.json  ← 12 real records from kratos_data CSV
  trust_irr_misclassification/
    incident.json
    controls.json
    job_run.json
    logs/TRUST-DAILY-BATCH-20260316.log
    sample_data/accounts.json  ← 10 Trust_Irrevocable records
  wire_mt202_drop/
    incident.json
    controls.json
    job_run.json
    logs/WIRE-NIGHTLY-RECON-20260316.log
    sample_data/accounts.json  ← 8 high-value business records

dashboard/src/
  components/
    ScenarioSelector.tsx       ← left-panel: scenario + job picker
    ControlScanPanel.tsx       ← control findings table
    RcaTracePanel.tsx          ← hop-by-hop backtracking viz
    IncidentCard.tsx           ← structured incident display
    RecommendationList.tsx     ← ranked recommendations
    ConfidenceGauge.tsx        ← E×T×D×H breakdown widget
  hooks/
    useInvestigation.ts        ← SSE stream consumer for /demo/stream/{id}
    useScenarios.ts            ← fetches /demo/scenarios
  pages/
    DemoPage.tsx               ← full demo layout (replaces or extends DemoRCA.tsx)
```

---

## CRITICAL RULES — ALWAYS FOLLOW

### 1. Ontology is frozen — never extend it
`causelink/ontology/schema.py` contains **19 canonical node labels** and
**26 canonical relationship types**. These are frozensets. You must NEVER add
new labels or rel-types. Map every new concept to an existing label.

**Valid node labels:**
`Job | Pipeline | Incident | Violation | Rule | Table | Column | Module |
Artifact | Control | Cluster | Config | Schema | JobStep | Report |
Classifier | Party | Account | Regulation`

**Valid relationship types:**
`RUNS_JOB | DEPENDS_ON | MANDATES | TRIGGERED_BY | IMPLEMENTED_IN |
VALIDATES | OWNS | REPORTS_TO | GENERATES | CONSUMES | MONITORS | ALERTS |
CLASSIFIES | AGGREGATES | ROUTES | SCREENS | RECONCILES | AUDITS | CERTIFIES |
REFERENCES | INHERITS | OVERRIDES | SCHEDULES | PERSISTS | INDEXES | ARCHIVES`

### 2. InvestigationState is append-only
Never mutate existing fields. Always use `.append()` on list fields.
Never replace `audit_trace`, `evidence_objects`, `hypotheses`, or `causal_edges`.
New entries only.

### 3. Pattern-first hypotheses
Never create a `Hypothesis` object without a matching `pattern_id` from
`HypothesisPatternLibrary`. The 3 demo patterns are:
- `AGG_STEP_DISABLED` → fires when log contains "skipped (disabled in JCL)"
- `IRR_NOT_IMPLEMENTED` → fires when log contains "fallback ORC=SGL"
- `MT202_HANDLER_MISSING` → fires when log contains "silently dropped"

### 4. ValidationGate before root_cause_final
Never set `root_cause_final` or `status=CONFIRMED` without passing all R1–R8
gates in `causelink/validation/gates.py`. Always call `ValidationGate.run(state)`
and check `.all_passed` before promoting.

### 5. Confidence formula is fixed
```python
# E×T×D×H weights — never change these
EVIDENCE_WEIGHT    = 0.40
TEMPORAL_WEIGHT    = 0.25
DEPTH_WEIGHT       = 0.20
HYPOTHESIS_WEIGHT  = 0.15

# composite_confidence threshold for CONFIRMED status
CONFIRMATION_THRESHOLD = 0.70
```

### 6. Pydantic v2 only
All models use `pydantic.BaseModel` v2 style.
Use `model_validator`, `field_validator`, `model_config = ConfigDict(...)`.
Never use v1 `@validator`, `@root_validator`, or `class Config`.

### 7. Async FastAPI
All FastAPI endpoints are `async def`. Use `asyncio` throughout.
Database calls use `asyncpg` (kratos-data) or async Neo4j driver (kratos-agents).
Never use synchronous `requests` inside endpoint handlers.

### 8. TypeScript strict mode
All dashboard code uses TypeScript strict mode (`"strict": true` in tsconfig).
No `any` types. No `// @ts-ignore`. Define explicit interfaces for all API shapes.

### 9. Never touch operational_systems source files
`operational_systems/` is a **read-only mock**. You reference its defects and
artifacts but never modify its COBOL, Java, Python, SQL, or config files.
The integration layer reads and references them — it does not change them.

### 10. No PII in any output
Never include real SSNs, EINs, or actual account numbers in generated code,
test data, or log mock files. The CSV data uses synthetic names and UUIDs only.

---

## THREE DEMO SCENARIOS — MEMORIZE THESE

### Scenario 1: `deposit_aggregation_failure`
- **Anchor:** `INC-001` (Incident node)
- **True root cause:** `AGGRSTEP` (Step 3) commented out in
  `operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl`
- **Defect ID:** `DEF-LDS-001`
- **Control failed:** `C2` (Coverage Calculation Accuracy — 12 CFR § 330.1(b))
- **Key log signal:** `"AGGRSTEP — skipped (disabled in JCL)"`
- **Pattern:** `AGG_STEP_DISABLED`
- **CanonGraph path (6 hops):**
  `INC-001 →[TRIGGERED_BY]→ CTL-C2 →[MANDATES]→ RUL-AGG →[DEPENDS_ON]→
   PIP-DIJ →[RUNS_JOB]→ STP-AGG →[IMPLEMENTED_IN]→ ART-JCL`
- **Real data impact:** 1,951 of 6,006 accounts (32.5%) exceed SMDIA
  without proper depositor-level aggregation

### Scenario 2: `trust_irr_misclassification`
- **Anchor:** `INC-002` (Incident node)
- **True root cause:** IRR branch not implemented in
  `operational_systems/trust_custody_system/cobol/TRUST-INSURANCE-CALC.cob`
  and `java/BeneficiaryClassifier.java` (IRR → SGL fallback in switch)
- **Defect ID:** `DEF-TCS-001`
- **Control failed:** `A3` (Fiduciary Documentation — 12 CFR § 330.13)
- **Key log signal:** `"fallback ORC=SGL (IRR not implemented)"`
- **Pattern:** `IRR_NOT_IMPLEMENTED`
- **CanonGraph path (6 hops):**
  `INC-002 →[TRIGGERED_BY]→ CTL-A3 →[MANDATES]→ RUL-IRR →[DEPENDS_ON]→
   PIP-TDB →[RUNS_JOB]→ ART-COB →[DEPENDS_ON]→ ART-BCJ`
- **Real data impact:** 253 Trust_Irrevocable accounts in CSV,
  coverage gap ~$61.8M across full dataset

### Scenario 3: `wire_mt202_drop`
- **Anchor:** `INC-003` (Incident node)
- **True root cause:** `parse_message()` in
  `operational_systems/wire_transfer_system/python/swift_parser.py`
  handles MT103 only — no else/raise for MT202/MT202COV
- **Defect ID:** `DEF-WTS-001`
- **Control failed:** `B1` (Daily Balance Snapshot — 12 CFR § 370.4(a)(1))
- **Key log signal:** `"silently dropped (no handler)"`
- **Pattern:** `MT202_HANDLER_MISSING`
- **CanonGraph path (6 hops):**
  `INC-003 →[TRIGGERED_BY]→ CTL-B1 →[MANDATES]→ RUL-SWF →[DEPENDS_ON]→
   PIP-WNR →[RUNS_JOB]→ MOD-SWP →[IMPLEMENTED_IN]→ ART-SWP`
- **Real data impact:** GL break $284,700,000 — 47 MT202 + 12 MT202COV dropped

---

## KNOWN OPERATIONAL SYSTEM DEFECTS — REFERENCE ONLY

When generating recommendations, always cite the exact defect ID and artifact path:

```
DEF-LDS-001  batch/DAILY-INSURANCE-JOB.jcl          Step 3 AGGRSTEP commented out
DEF-LDS-002  cobol/ORC-ASSIGNMENT.cob                IRR ORC not implemented
DEF-LDS-003  java/DepositService.java                EBP flat $250K not per-participant
DEF-LDS-004  batch/DAILY-INSURANCE-JOB.jcl           comma delimiter instead of pipe
DEF-LDS-005  java/DepositService.java                PII SSN/EIN in plaintext output
DEF-TCS-001  cobol/TRUST-INSURANCE-CALC.cob          IRR falls back to SGL
DEF-TCS-002  config/trust-config.properties          REV beneficiary cap = 5 (stale)
DEF-TCS-003  java/BeneficiaryClassifier.java         IRR → SGL in switch statement
DEF-TCS-004  config/trust-config.properties          include_deceased=true
DEF-TCS-005  config/trust-config.properties          grantor_level.enabled=false
DEF-TCS-006  sql/sp_calculate_trust_insurance.sql    sub-account balances excluded
DEF-WTS-001  python/swift_parser.py:parse_message()  MT202/MT202COV silently dropped
DEF-WTS-002  config/wire-config.properties           OFAC batch mode 6-hour delay
DEF-WTS-003  python/ofac_screening.py                SDN list weekly, missing EU/UK/UN
DEF-WTS-004  python/ofac_screening.py                fuzzy/phonetic matching disabled
DEF-WTS-005  java/WireTransactionService.java        book transfers bypass insurance
DEF-WTS-006  python/swift_parser.py                  field 77B ignored
DEF-WTS-007  python/reconciliation.py                nostro accounts not matched
DEF-XSY-001  ALL SYSTEMS                             no cross-channel depositor aggregation
DEF-XSY-002  ALL SYSTEMS                             SMDIA hardcoded $250,000
DEF-XSY-003  ALL SYSTEMS                             no 24-hour deadline tracking
```

---

## DATA LAYER — CSV PROFILE

File: `data/kratos_data_20260316_1339.csv`
- **6,006 rows**, 11 columns, all quality checks PASS
- **Columns:** `party_id, name, party_type, party_status, account_id,
  account_number, account_type, account_status, current_balance,
  account_open_date, orc_code`
- **All party_type = Individual** (known issue: business ORC codes on individual
  parties = ORC_PARTY_MISMATCH — do not treat as a data error in your code,
  treat as a compliance finding)
- **Key ORC counts:** Single:879, Joint_JTWROS:601, Business_LLC:476,
  IRA_Traditional:444, IRA_Roth:443, Trust_Irrevocable:253
- **SMDIA exposures:** 1,951 accounts with balance > $250,000
- **Total AUM:** $1,320,961,508.99
- **Date range:** 2016-03-07 to 2026-03-05

When loading this CSV as evidence, map columns to `EvidenceObject` fields:
```python
EvidenceObject(
    evidence_id=str(uuid4()),
    source_system="kratos_data_csv",
    source_file="data/kratos_data_20260316_1339.csv",
    entity_type="account",
    entity_id=row["account_id"],
    tier="SIGNAL",   # or CRITICAL if balance > 250000 and orc requires aggregation
    content={...},   # full row as dict
    timestamp=datetime.fromisoformat(row["account_open_date"])
)
```

---

## API CONTRACTS — NEW DEMO ENDPOINTS

Build these in `src/demo_api.py` (FastAPI, port 8002):

```
GET  /demo/scenarios
     → List[ScenarioSummary]
     Returns available scenarios with metadata

GET  /demo/scenarios/{scenario_id}
     → ScenarioDetail
     Returns full scenario pack (incident, controls, job_run, sample accounts)

POST /demo/investigations
     Body: { "scenario_id": str, "job_id": str }
     → { "investigation_id": str, "status": "STARTED" }
     Starts a new demo RCA investigation

GET  /demo/investigations/{investigation_id}
     → InvestigationState (full)
     Returns current state

GET  /demo/investigations/{investigation_id}/trace
     → List[AuditEntry]
     Returns audit trail only

GET  /demo/investigations/{investigation_id}/graph
     → CanonGraph
     Returns ontology graph for visualization

GET  /demo/stream/{investigation_id}
     → SSE stream of InvestigationState deltas, one event per phase
     Event format: data: {"phase": "LOGS_FIRST", "state_delta": {...}}

GET  /demo/controls/{scenario_id}
     → ControlScanResult
     Returns control findings for the scenario without starting full RCA
```

All endpoints return JSON. All list endpoints return `{"items": [...], "total": N}`.
All error responses follow: `{"error": "CODE", "message": "...", "detail": {...}}`.

---

## FRONTEND CONTRACT

The React dashboard (`dashboard/src/`) uses **Vite + TypeScript + strict mode**.
Component library: none (plain CSS modules or Tailwind if already configured).
State management: React hooks only — no Redux, no Zustand.
API calls: native `fetch` with typed response shapes — no axios.

SSE consumer pattern (use this exactly):
```typescript
// hooks/useInvestigation.ts
const useInvestigation = (investigationId: string) => {
  const [phases, setPhases] = useState<PhaseResult[]>([]);

  useEffect(() => {
    const es = new EventSource(`/demo/stream/${investigationId}`);
    es.onmessage = (e) => {
      const delta: PhaseResult = JSON.parse(e.data);
      setPhases(prev => [...prev, delta]);
    };
    return () => es.close();
  }, [investigationId]);

  return phases;
};
```

ScenarioSelector layout (left panel, always visible):
```
┌─────────────────────────┐
│  Select Scenario        │
│  ○ deposit_aggregation  │
│  ○ trust_irr_misclass   │
│  ○ wire_mt202_drop      │
├─────────────────────────┤
│  Job ID                 │
│  [DAILY-INSURANCE-JOB-  │
│   20260316            ] │
├─────────────────────────┤
│  [ Run RCA Analysis ] ↗ │
└─────────────────────────┘
```

RcaTracePanel renders each backtracking hop as a node row:
```
● INC-001  Incident         overstated_coverage          [CONFIRMED FAILED]
  ↓ TRIGGERED_BY
● CTL-C2   Control          C2 Coverage Accuracy         [CONFIRMED FAILED]
  ↓ MANDATES
● RUL-AGG  Rule             depositor_aggregation        [CONFIRMED FAILED]
  ↓ DEPENDS_ON
● PIP-DIJ  Pipeline         DAILY-INSURANCE-JOB          [CONFIRMED FAILED]
  ↓ RUNS_JOB
◉ STP-AGG  JobStep          AGGRSTEP (DISABLED)          [ROOT CAUSE]
  ↓ IMPLEMENTED_IN
◉ ART-JCL  Artifact         DAILY-INSURANCE-JOB.jcl:3   [CONFIRMED DEFECT]
```

---

## CODE GENERATION RULES

When Copilot generates code in this workspace:

1. **Read imports from existing files first.** If generating a new agent class,
   look at `src/causelink/agents/evidence_collector.py` for the import style
   and class signature pattern. Mirror it exactly.

2. **Use `InvestigationState` as the bus.** Every agent method signature is:
   `async def run(self, state: InvestigationState) -> InvestigationState`
   Always return the mutated state. Never return None.

3. **Log every action to audit_trace.** Every time an agent accepts or rejects
   evidence, hypotheses, or edges, append to `state.audit_trace`:
   ```python
   state.audit_trace.append(AuditEntry(
       phase=PhaseEnum.LOGS_FIRST,
       agent="EvidenceCollectorAgent",
       action=AuditAction.ACCEPTED,   # or REJECTED
       evidence_id=obj.evidence_id,
       reason="matched pattern AGG_STEP_DISABLED"
   ))
   ```

4. **Scenario pack loading is synchronous.** JSON files are small — load with
   `json.load(open(...))` in `ScenarioLoader.__init__`. No async needed.

5. **CanonGraph seeding is deterministic.** `ScenarioSeeder.seed(scenario_id)`
   returns a hardcoded `CanonGraph` — no DB call, no randomness. The graph is
   defined in `demo/ontology/canon_graphs.py` as a dict of node+edge lists.

6. **SSE streaming pushes one event per phase.** Each of the 7 phases emits one
   SSE event when complete. Use `asyncio.Queue` inside the service and an async
   generator in the FastAPI endpoint:
   ```python
   async def stream_investigation(investigation_id: str):
       async def event_generator():
           async for delta in demo_service.stream(investigation_id):
               yield f"data: {delta.model_dump_json()}\n\n"
       return StreamingResponse(event_generator(), media_type="text/event-stream")
   ```

7. **Confidence calculator is pure.** `ConfidenceCalculator.compute(evidence,
   temporal, depth, hypothesis)` takes four [0,1] floats and returns a float.
   No side effects, no I/O, no state. Fully unit-testable.

8. **Tests use pytest + pytest-asyncio.** Test files go in `tests/demo/`.
   Fixture pattern: `@pytest.fixture` for scenario packs, `AsyncMock` for
   any external calls. Target 80% coverage on new demo/ code.

---

## SUGGESTED BUILD ORDER (follow this sequence)

```
Phase A — Data layer (no external deps)
  1. demo/ontology/canon_graphs.py        ← hardcoded CanonGraph per scenario
  2. demo/loaders/scenario_loader.py      ← loads JSON packs from scenarios/
  3. demo/loaders/csv_evidence_loader.py  ← loads CSV → List[EvidenceObject]
  4. demo/loaders/operational_adapter.py  ← defect registry → CanonNode refs

Phase B — Service layer
  5. demo/ontology/scenario_seeder.py     ← seeds InvestigationState.canon_graph
  6. demo/services/control_scanner.py     ← scans controls.json → ControlScanResult
  7. demo/services/confidence_calculator.py ← E×T×D×H formula
  8. demo/services/demo_rca_service.py    ← 7-phase orchestration

Phase C — New pattern registrations
  9. causelink/patterns/library.py        ← ADD 3 new patterns (additive only)

Phase D — API
  10. src/demo_api.py                     ← FastAPI port 8002

Phase E — Frontend
  11. dashboard/src/hooks/useScenarios.ts
  12. dashboard/src/hooks/useInvestigation.ts
  13. dashboard/src/components/ScenarioSelector.tsx
  14. dashboard/src/components/ControlScanPanel.tsx
  15. dashboard/src/components/RcaTracePanel.tsx
  16. dashboard/src/components/IncidentCard.tsx
  17. dashboard/src/components/RecommendationList.tsx
  18. dashboard/src/components/ConfidenceGauge.tsx
  19. dashboard/src/pages/DemoPage.tsx

Phase F — Tests
  20. tests/demo/test_scenario_loader.py
  21. tests/demo/test_canon_graphs.py
  22. tests/demo/test_demo_rca_service.py
  23. tests/demo/test_confidence_calculator.py
  24. tests/demo/test_demo_api.py
```

---

## WHAT NOT TO DO

- Do NOT modify `causelink/ontology/schema.py` — it is frozen
- Do NOT add new fields to `InvestigationState` without checking
  `causelink/state/investigation.py` for the existing shape first
- Do NOT call Neo4j in demo mode — demo uses `canon_graphs.py` (in-memory)
- Do NOT use `OpenAI` API in demo mode — all reasoning is deterministic/pattern-based
- Do NOT create new Pydantic model files — extend existing ones in `schemas.py`
  or `causelink/rca/models.py`
- Do NOT hardcode port numbers in source — read from environment variables
  with defaults: `DEMO_API_PORT=8002`, `CAUSELINK_PORT=8001`, `RCA_PORT=8000`
- Do NOT use `print()` for logging — use `logging.getLogger(__name__)`
- Do NOT commit the CSV file to git history — it should be in `.gitignore`

---

## EXTENSION HOOKS (build these in from day one)

The 3-scenario demo must be structured so adding a 4th scenario requires only:
1. Adding a new folder under `scenarios/` with the 5 JSON/log files
2. Adding a new `CanonGraph` entry in `demo/ontology/canon_graphs.py`
3. Adding a new pattern in `causelink/patterns/library.py`

No changes to the service layer, API layer, or frontend for new scenarios.
The `ScenarioRegistry` auto-discovers scenario folders at startup.
The `ScenarioSelector` component fetches the list from `GET /demo/scenarios`.

---

*Kratos Intelligence Platform — Copilot Workspace Instructions*
*FDIC Part 370/330 Compliance · CauseLink RCA · Legacy Systems Analysis*
*All data is synthetic. Not for production regulatory use.*
