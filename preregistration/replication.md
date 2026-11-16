# v4: pre-registered confirmatory replication of the v3 findings

This document fixes the hypotheses, the source-selection procedure, the case-construction rule and the analysis. It was written and committed before any v4 source was fetched; the git commit time is authoritative. Every v4 run uses the code frozen at v3 (`src/decisiongap/applicability.py`, `tools/run_natural.py`, `tools/run_applicability.py`, `tools/natural_analysis.py`) without modification.

## Hypotheses (from v3)

- **H1, persistence.** Supported-but-inapplicable errors, as audited per case, make up a larger share of wrong decisions for the stronger assistants (Qwen3.5-9B, Qwen3-4B) than for the weaker ones (Qwen2.5-1.5B, SmolLM2-1.7B).
  - Test: the pooled share among wrong answers of the two stronger models versus the two weaker models, with a Fisher exact test (one-sided, in the stated direction).
- **H2, verification with the user's situation.** The checklist judge and QBR (`source_bound`) correct a larger share of supported-but-inapplicable errors than the qualifier rules leave uncorrected, without lowering decision accuracy below no verifier.
  - Measured on the Qwen3-4B answers (primary) and the Qwen3.5-9B answers (self-verification).
- **H3, certificate soundness.** Certified decisions under QBR `source_bound` are correct at a rate of at least 90%, with coverage reported.

## Source selection (systematic; fixed before fetching)

- **Finance.**
  - Query: SEC EDGAR full-text search for 8-K filings dated 2026-10-01 to 2026-11-14 whose text contains "constant currency" or "non-GAAP operating margin".
  - Selection: in the order EDGAR returns them, take the first 10 distinct companies that meet all three conditions:
    - not used in v1, v2 or v3 (Procore, Workiva, Protolabs, Dexcom, Figma, EMCOR, Crocs, Hinge Health, ADTRAN, RCI, Zoom, Lululemon, Nike, Datadog, Garmin);
    - the filing has an earnings-release exhibit (EX-99.1);
    - its highlights print at least one condition pair from the list below.
- **Medicine.**
  - Query: PubMed `randomized controlled trial[pt] AND 2026[dp] AND hasabstract AND ("absolute risk reduction" OR "per-protocol" OR "subgroup" OR "aged")`.
  - Selection: in PubMed's order, take the first 8 abstracts that print a condition pair below, excluding every PMID used before.

## Condition pairs (one item per pair, at most 3 items per source, taken in order of appearance)

- **Finance:**
  - GAAP vs non-GAAP (margin or EPS);
  - reported vs constant currency;
  - segment or region vs consolidated;
  - quarter vs year to date;
  - reported vs outlook (guidance).
- **Medicine:**
  - relative vs absolute effect;
  - intention-to-treat vs per-protocol;
  - subgroup vs overall;
  - one outcome vs another.

## Case construction (mechanical)

1. **Assign the two values.** In each pair, X is the value printed first in the excerpt and Y is the other value. Both must be printed verbatim, or for a difference, computable from two printed rates.
2. **Write the three situations.** The decision is "at least L".
   - A: the user's condition matches X, with L = (X+Y)/2.
   - B: the user's condition matches Y, with the same L.
   - C: the user's condition matches Y, with L moved past Y by |X−Y|/2 in the direction that reproduces A's decision.
3. **Applicable and trap values.** In each case the applicable value is the one whose condition matches the user; the trap is the other value.
4. **Wording.** Situations use a fixed template per family, written once before any v4 source is read.
5. **Excerpts.** A finance excerpt is the highlights section that contains both values. A medicine excerpt is the full abstract.

## Runs (identical to v3)

- **Assistants.** Qwen3-4B, Qwen2.5-1.5B, SmolLM2-1.7B on CPU, and Qwen3.5-9B on GPU, with the same prompt, schema, seed and temperature.
- **Verifiers.**
  - On Qwen3-4B's and Qwen3.5-9B's answers: rules, LLM judge, checklist judge, QBR (with the bound_first, judge_only and `source_bound` policies computed from the same calls).
- **Typing.** The automatic typing is the same as in v3, and every wrong answer, plus every right answer that cites the trap value, gets a per-case audit with a written reason, using the v3 categories.

## Reporting

- **What is reported.** All outcomes are reported, including H1–H3 if they fail.
- **Pooling.** v3 and v4 may be pooled for descriptive totals only after reporting v4 on its own.
- **Freeze.** No item, prompt, threshold or code is changed after any v4 output is seen.
