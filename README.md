# Supported Is Not Applicable: Decision-Level Failures in Cited AI Advice

Hsu, Chin Hao · National Tsing Hua University · Apart Research AI × Epistemics Research Sprint, 2026

Paper: [`paper/supported-is-not-applicable.pdf`](paper/supported-is-not-applicable.pdf)

## Problem

Citation verification checks that a source supports a claim. In advice, a supported number can still be wrong for the user, because the source prints it under a condition that does not hold for that user. Asana prints *"$10.99 per user, per month billed annually. $13.49 billed monthly"*; an assistant that tells a five-person team paying monthly that Starter fits a $60 limit quotes the page faithfully and is wrong ($67.45). The study separates four properties of a cited recommendation: the source prints the value (S), the quote is faithful (C), the printed condition holds for the user (A), the decision is correct (D). The failure studied is S = 1, A = 0, D = 0.

## What was done

- **Benchmarks.** Items are built from verbatim SaaS pricing pages, SEC 8-K earnings releases and PubMed abstracts. Each item fixes one excerpt and three user situations: in A the printed condition holds; in B it does not and the applicable printed value flips the decision; in C it does not and the decision stands. Gold decisions are computed from printed values.
- **Controlled evaluation.** In the contrast and held-out sets the assistant answer is a template that decides from the headline value. Verifiers are scored by the decision the user ends with: wrong answers fixed (B) and harmless mismatches left alone (C).
- **Natural answers.** Four open assistants (SmolLM2-1.7B, Qwen2.5-1.5B, Qwen3-4B, Qwen3.5-9B) write cited answers on unseen sources. Every wrong answer is audited with a written reason into supported-but-inapplicable, ambiguous, other printed value, arithmetic or reasoning error, unfaithful quote, or no answer. The discovery set produced the hypotheses; the replication tested them on sources chosen by a fixed EDGAR / PubMed rule.
- **Verifiers.** NLI cross-encoders and Lynx-8B (claim-to-source checks), a qualifier rule, an LLM judge, a checklist judge, DCV, and QBR (quote-bound recalculation: the model lists operands with verbatim quotes, code binds each operand to a printed clause and its condition and certifies the decision by evaluating the expression). All LLM verifiers use Qwen3.5-9B.
- **Statistics.** Intervals on natural answers bootstrap source documents; H1 is reported as the share of wrong decisions and as the rate per answer; verifiers are compared by paired accuracy difference; certificate precision has an exact binomial interval.

## Results

- **Capable assistants still make the error.** Replication (41 items, 123 cases): the two strongest assistants made 25 wrong decisions in 246 answers and the two weakest 119; supported-but-inapplicable errors were 9 and 14, so they rose from 14/119 to 9/25 of wrong decisions (pre-registered one-sided Fisher p = 0.0057; source-clustered 95% interval of the difference [−9, +63] points). Discovery: 5 vs 38 wrong decisions, 4 vs 5 inapplicable.
- **Claim-to-source checks cannot see it.** Contrast test split (69 cases): NLI 31/69 and Lynx-8B 40/69, against 45/69 with no verifier. The qualifier rule fixes 21/24 wrong answers and overturns all 21 harmless mismatches.
- **Verification against the user's situation raises accuracy but misses many of these errors.** On Qwen3-4B's replication answers the checklist judge gains 3 points (95% CI [+1, +6]) and corrects 2 of 5 inapplicability errors; the three it misses are errors its own model makes when answering.
- **Two evaluation practices overstate verification.** The checklist judge scores 65/69 on the contrast set and 34/45 on the held-out set (no verifier 30/45). QBR certified 3 of 10 held-out decisions from computations that used no source value; with a source-dependence check, it withheld 3 of 23 replication certificates, and certified decisions were correct in 36/36 discovery and 19/20 replication cases.

## Benchmark sets

| Folder | Items / cases | Domains | Role |
|---|---|---|---|
| `data/contrast` | 30 / 86 | pricing, finance, medicine | Template answers; 24-item test split; verifier development |
| `data/contrast/items_long.jsonl` | 22 / 66 | pricing, finance, medicine | Contrast items with ~12k-character excerpts |
| `data/heldout` | 15 / 45 | pricing, finance | Held-out test of QBR, evaluated once |
| `data/discovery` | 17 / 51 | finance, medicine | Natural answers; discovery |
| `data/replication` | 41 / 123 | finance, medicine | Natural answers; pre-registered replication |

The held-out evaluation, the discovery set and the replication (hypotheses H1–H3, source-selection rule, case construction) were pre-registered, and the certainty-probe design fixed, before each ran; the documents are in `preregistration/`.

## Repository

| Path | Contents |
|---|---|
| `paper/` | PDF, LaTeX source, `numbers.tex` (every number in the paper, generated from `results/`), figures |
| `data/<set>/` | `items.jsonl`, `build.py`; for natural sets also `answers/<assistant>.jsonl` (raw assistant outputs) and `answered/<assistant>.jsonl` (verifier inputs) |
| `data/sources/` | Source snapshots: pricing-page text, SEC releases, PubMed XML, and the ordered EDGAR / PubMed candidate lists used to select replication sources |
| `results/<set>/` | One file per verifier with a verdict per case (contrast sets prefix the split, e.g. `test_qbr.jsonl`), `*_raw.jsonl` with the full model calls, and the scored summary |
| `results/<natural set>/` | `verifiers/<assistant>/`, `audit/<assistant>.json` (audit label and reason per case), `analysis.json`, `statistics.json` |
| `results/` | `gold_check.json`, `masked_reaudit/`, `certainty_probe/`, `qbr_certificates.json` |
| `src/applicability.py` | All verifiers and the assistant call |
| `scripts/` | Runners (`run_verifiers.py`, `run_assistants.py`, `run_nli.py`, `run_lynx.py`, `certainty_probe.py`), analyses, figure and number generators, `reproduce.sh` |
| `config/` | Model, server and decoding settings for the verifier and Lynx |

## Reproduce

```bash
pip install -r requirements.txt
bash scripts/reproduce.sh            # every number and figure in the paper from the logged outputs, then the PDF (tectonic)
python data/replication/build.py     # each set rebuilds byte for byte from data/sources
```

Model runs use llama.cpp `llama-server` with Q4_K_M GGUF weights in `models/`, temperature 0, seed 20261115:

| Role | Model | Server |
|---|---|---|
| Verifier and 9B assistant | Qwen3.5-9B (`unsloth/Qwen3.5-9B-GGUF`) | port 8083, `config/verifier.json` |
| Assistants | Qwen3-4B-Instruct-2507, Qwen2.5-1.5B-Instruct, SmolLM2-1.7B-Instruct | port 8085, started by `run_assistants.py` |
| Faithfulness baseline | Lynx-8B (`PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct-Q4_K_M-GGUF`) | port 8084, `config/lynx.json` |
| Support baseline | `cross-encoder/nli-deberta-v3-small` (ONNX) | in-process, `models/nli-deberta-v3-small/` |

```bash
python scripts/run_assistants.py --set replication --model qwen3-4b
python scripts/make_audit_sheet.py --set replication --model qwen3-4b
python scripts/run_verifiers.py --set replication --assistant qwen3-4b --arms rules,judge,judge_checklist,qbr
python scripts/run_verifiers.py --set contrast --split test --arms rules,judge,judge_checklist,dcv,direct,qbr
python scripts/run_nli.py --split test
python scripts/run_lynx.py --split test
```

## License

MIT for code and data. Lynx-8B weights are CC-BY-NC-4.0.
