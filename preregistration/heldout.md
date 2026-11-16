# v2 held-out evaluation: pre-registration (written before any QBR result on v1 and before any run on v2)

Date: 2026-11-15, Taipei. Data: datasets/applicability/items_v2.jsonl (frozen at commit c1fd472).

## Method selection (on v1 only)
- Strict quote-bound recalculation (QBR) is run on all 86 v1 cases (dev + test), which are development data for QBR.
- Primary QBR policy = the one of {bound_first, agree, judge_only} with the highest v1 decision accuracy.
  Ties: bound_first, then agree. All three come from the same model call, so the other two are reported as ablations.
- After selection the code is committed and not changed before the v2 run.

## v2 run (once)
- Arms: rules, judge (situation-aware), judge_checklist (main rival), qbr, dcv (frozen v1 method), direct.
- Same local model, prompts and seeds as v1. No re-runs after seeing v2 results, except to resume an interrupted run.
- Primary endpoint: decision accuracy on the 45 v2 cases; paired exact McNemar vs judge_checklist; item-level bootstrap CI.
- Secondary: B caught and fixed, C kept, A false alarms, wrong interventions on right answers, QBR strata
  (decided by verified code / judge fallback / insufficient / defer) with accuracy per stratum.

## Disclosure
- v2 pricing pages were not in v1 but were among the 37 pages used while developing the DecisionGap product;
  the two finance releases (Crocs, Hinge Health) were never used before. The condition types in 12 of 15 items
  were not named in any prompt or checklist.
- While writing QBR's binding unit checks, two phrases from v2 excerpts (Crocs wholesale growth, Supabase MAU
  overage) were used as test strings for clause splitting. No model was run on v2.

## Selection result (v1 development data, recorded before the v2 run)
- Strict QBR, after label clarification and offline verifier changes on v1 only (condition compatibility over five
  dimensions, per-unit scaling check, only operands used by the computation are checked).
- v1 dev + test (86 cases): bound_first 79/86, agree 76/86, judge_only 76/86 -> primary policy: bound_first.
- On v1 test: QBR 63/69; its own judge verdict (same call) 60/69; checklist judge (separate prompt) 65/69.
  Verified-code decisions were right in 46/46 (test) and 11/11 (dev) cases. 2 QBR calls hit the output limit
  (repetition loop) and are counted as errors.
- An earlier QBR prompt (ambiguous 'insufficient' label) scored 12/17 on dev; its outputs are kept in
  results/applicability/qbr_v0_superseded/.

## Post-run disclosure (added 2026-11-15, after the v2 run; nothing above was edited)

- During the final review of the paper, an n-gram scan of the code against v2-only text found that QBR_INSTRUCTIONS
  in src/decisiongap/applicability.py (added in commit 106a0dc, after the v2 freeze and before the v2 run) quotes one
  v2 phrase, "then $0.125 per GB" (item v2-supabase-disk), as an example of condition words. It was not listed above.
  QBR scored 2/3 on that item, and judge_checklist 3/3. No other v2-only 3- or 4-gram containing a number, and no 6-gram,
  occurs in the prompts, tools or tests. No method was changed or re-run because of this finding.
