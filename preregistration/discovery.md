# v3 natural-answer study: pre-registration

Written and committed 2026-11-15 21:48:48 +0800 (commit `0fbb2b4`). Correction added 22:05 the same evening: an earlier version of this line said "about 22:40". That was a wrong estimate; the commit timestamp is authoritative, and the first v3 assistant call was logged at 21:50. It was committed together with the frozen data and code before any assistant or verifier ran on v3. The only v3-like call made beforehand was a smoke test on a toy item that is not part of v3.

## Question

The earlier sets used templated answers that always quote the headline value. This study asks what happens when real assistant models write the cited answers themselves:

1. How often do the answers contain supported-but-inapplicable errors?
2. How do verifiers perform on those answers?

## Data

The data file is `datasets/applicability/items_v3.jsonl`, built by `build_v3.py`. It has 17 items and 51 cases:

- 12 finance items;
- 5 medicine items.

### Sources

No item in v1, v2 or the long-document set uses any of these sources, and no prompt quotes them.

- **New for v3:** SEC 8-K earnings releases from Zoom, Lululemon, Nike, Datadog and Garmin, fetched with `fetch_v3_releases.py`.
- **Downloaded during v2 construction but never used:** the ADTRAN and RCI releases.
- **From the earlier PubMed download files:** abstracts 40931979, 42992175 and 42894628. No item used them.

### Case design

- **Situations.** Each item has three user situations:
  - A: the headline value's condition holds for the user.
  - B: it does not, and the applicable printed value flips the decision.
  - C: it does not, but the decision is unchanged.
- **Gold labels.** Each gold decision follows by arithmetic from printed values. The builder asserts that every applicable value and every trap value is printed in the excerpt.
- **Condition families:**
  - from v1: GAAP basis, reporting period, relative vs absolute effect, population scope;
  - from v2: currency basis, segment vs consolidated, guidance vs reported;
  - new in v3: outcome mismatch, and analysis population (per-protocol vs intention-to-treat).

## Assistants (answer writers)

All assistants run with temperature 0, seed 20261115, JSON-schema output (explanation, quote, decision), the same system prompt (`ASSIST_SYSTEM`), and decision options limited to the binary choice.

| Assistant | Hardware | Port | Role |
|---|---|---|---|
| Qwen3-4B-Instruct-2507 Q4_K_M | CPU | 8085 | primary |
| Qwen2.5-1.5B-Instruct Q4_K_M | CPU | 8085 | |
| SmolLM2-1.7B-Instruct Q4_K_M | CPU | 8085 | |
| Qwen3.5-9B | | | optional, if time permits; also the verifier model, so it is reported separately |

## Outcomes

- **P1, prevalence (all assistants).** For each assistant and label (A/B/C):
  - the share of wrong decisions;
  - among wrong B decisions, the share typed `supported_inapplicable`, assigned automatically by `type_error` in `tools/run_natural.py` (the answer cites the trap value but not the applicable one).
  - These rates are reported with Wilson 95% intervals.
- **P2, verifiers (primary assistant: Qwen3-4B).**
  - Decision accuracy after verification for: no verifier, qualifier rules, plain LLM judge, checklist judge, and QBR under policy `source_bound`.
  - `source_bound` is the v3 primary QBR policy: bound_first plus the requirement that a certified expression uses at least one source operand. It is fixed in this commit and was derived from the v2 failures.
  - QBR bound_first and QBR judge_only are reported as well.
  - Statistics: item-bootstrap 95% intervals, and exact McNemar tests of QBR (`source_bound`) vs the checklist judge.
- **P3, certificate soundness.** The share of correct certified decisions under `source_bound`, with its coverage.
- **Secondary.** If time permits, the same verifiers are run on Qwen2.5-1.5B's answers.

## Rules

- No method, prompt, scorer, typing rule or item is changed after any v3 output is seen. Runs may only be resumed after an interruption.
- Every v3 result is reported, including null and negative results.
