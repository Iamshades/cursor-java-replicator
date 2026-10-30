# PLAN: <KEY> - <summary>

Spec: `REPLICATION-SPEC.md` (approved by __ on __)
Mode: __ | Target: __ | Baseline: Java __ / Boot __ / Batch __
Build runs approved: yes/no | Command: `./mvnw -q -o test`

## Tasks

| ID | Task | Files | Covers | Verify | Status |
| --- | --- | --- | --- | --- | --- |
| T-01 | Characterization test for anchor JOB-x on fixture F-1 | `src/test/.../XJobCharacterizationTest.java` | safety net | test passes on unchanged code | [ ] |
| T-02 | Output record + layout | `.../CreditNoteLine.java` | REQ-..-02 | unit test | [ ] |
| T-03 | Reader with delta D-01 | `.../CreditNoteJobConfig.java` | D-01, REQ-..-01 | reader test on H2 / Testcontainers | [ ] |
| T-04 | Processor rules RULE-001..004 + D-02 | `.../CreditNoteProcessor.java` | RULE-..., D-02 | one test per rule | [ ] |
| T-05 | Writer + trailer | | REQ-..-03 | golden file test | [ ] |
| T-06 | Job/step wiring, fault tolerance, restart | | implicit:anchor | `@SpringBatchTest` job test | [ ] |
| T-07 | Trigger (schedule/REST) | | REQ-.. | controller/scheduler test | [ ] |
| T-08 | Config per profile | `application*.yml` | | context loads per profile | [ ] |
| T-09 | Parity run vs anchor | `.replication/parity/` | all REUSE/ADAPT | compare_outputs.py | [ ] |

## Deferred

| ID | Reason | Follow-up |
| --- | --- | --- |

## Risks

| Risk | Mitigation |
| --- | --- |
