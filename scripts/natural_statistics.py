"""Source-clustered statistics for the natural-answer studies (no model calls). Complements analyze_natural.py.
    python scripts/natural_statistics.py --set replication   ->  results/replication/statistics.json
Units: cases of one item, and items of one source document, are dependent, so every interval bootstraps SOURCE DOCUMENTS
(item["source"][0]) and every test is reported with that caveat.
  rates      per assistant: wrong decisions and audited supported-but-inapplicable (SI) errors per ALL cases
             (missing answers count as wrong), with Wilson and source-cluster bootstrap 95% intervals
  H1         pre-registered quantity (SI share of wrong answers, strong 9B+4B vs weak 1.5B+1.7B) and the per-answer SI rate,
             both as differences with source-cluster bootstrap intervals, plus leave-one-source-out ranges
  contested  H1 recomputed without cases whose gold is flagged contestable or whose item is flagged template-ambiguous
  verifiers  per verifier: paired accuracy difference vs no verifier (source-cluster bootstrap CI), answers fixed and broken,
             answered-case and end-to-end accuracy
  QBR cert   coverage, precision with an exact (Clopper-Pearson) 95% interval, and net effect vs the judge verdict of the same call
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from math import comb, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_verifiers as R  # noqa: E402

DATA = ROOT / "data"
RES = ROOT / "results"
STRONG, WEAK = ("qwen35-9b", "qwen3-4b"), ("qwen2.5-1.5b", "smollm2-1.7b")
ALL = STRONG + WEAK
WRONG_CATS = ("no_answer", "unfaithful_quote", "supported_inapplicable", "ambiguous_value", "other_printed_value", "numeric_or_reasoning_error")
REPS, SEED = 4000, 7


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def binom_cdf(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k, n, a=0.05):
    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - binom_cdf(k - 1, n, p) < a / 2)
    upper = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p) > a / 2)
    return [round(lower, 3), round(upper, 3)]


def fisher_greater(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    return sum(comb(n1, x) * comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)


def boot_ci(clusters, stat):
    """clusters: list of cluster payloads; stat(list_of_payloads) -> float or None."""
    rng = random.Random(SEED)
    vals = []
    for _ in range(REPS):
        v = stat([clusters[rng.randrange(len(clusters))] for _ in clusters])
        if v is not None:
            vals.append(v)
    vals.sort()
    return [round(vals[int(.025 * len(vals))], 3), round(vals[int(.975 * len(vals))], 3)] if vals else None


def load(set_name):
    items = [json.loads(l) for l in open(DATA / set_name / "items.jsonl", encoding="utf-8")]
    src = {it["id"]: it["source"][0] for it in items}
    cases = [(it["id"], c["label"]) for it in items for c in it["cases"]]
    aud = {}
    for m in ALL:
        p = RES / set_name / "audit" / f"{m}.json"
        if p.exists():
            aud[m] = {(r["item"], r["label"]): r for r in json.loads(p.read_text(encoding="utf-8"))}
    return items, src, cases, aud


def per_source(cases, src, aud, models, exclude=frozenset()):
    """{source: [si, wrong, answers]} summed over models (answers = every case, missing answers included)."""
    out = defaultdict(lambda: [0, 0, 0])
    for m in models:
        for k in cases:
            if k in exclude:
                continue
            s = src[k[0]]
            out[s][2] += 1
            r = aud[m].get(k)
            if r and r["category"] in WRONG_CATS:
                out[s][1] += 1
                out[s][0] += r["category"] == "supported_inapplicable"
    return out


def h1_block(cases, src, aud, exclude=frozenset()):
    S, W = per_source(cases, src, aud, STRONG, exclude), per_source(cases, src, aud, WEAK, exclude)
    keys = sorted(set(S) | set(W))
    clusters = [(S.get(k, [0, 0, 0]), W.get(k, [0, 0, 0]), k) for k in keys]

    def tot(cl):
        s = [sum(c[0][i] for c in cl) for i in range(3)]
        w = [sum(c[1][i] for c in cl) for i in range(3)]
        return s, w

    def share_diff(cl):
        s, w = tot(cl)
        return None if s[1] == 0 or w[1] == 0 else s[0] / s[1] - w[0] / w[1]

    def rate_diff(cl):
        s, w = tot(cl)
        return s[0] / s[2] - w[0] / w[2]

    s, w = tot(clusters)
    loso = []
    for i in range(len(clusters)):
        rest = clusters[:i] + clusters[i + 1:]
        rs, rw = tot(rest)
        if rs[1] and rw[1]:
            loso.append((clusters[i][2], round(rs[0] / rs[1] - rw[0] / rw[1], 3),
                         round(fisher_greater(rs[0], rs[1] - rs[0], rw[0], rw[1] - rw[0]), 4)))
    return {"strong": {"si": s[0], "wrong": s[1], "answers": s[2]}, "weak": {"si": w[0], "wrong": w[1], "answers": w[2]},
            "si_share_of_wrong": {"strong": f"{s[0]}/{s[1]}", "weak": f"{w[0]}/{w[1]}",
                                  "difference": round(share_diff(clusters), 3) if share_diff(clusters) is not None else None,
                                  "difference_source_cluster_ci95": boot_ci(clusters, share_diff),
                                  "fisher_one_sided_p_treating_errors_as_independent": round(fisher_greater(s[0], s[1] - s[0], w[0], w[1] - w[0]), 4)},
            "si_per_answer": {"strong": f"{s[0]}/{s[2]}", "weak": f"{w[0]}/{w[2]}", "difference": round(rate_diff(clusters), 4),
                              "difference_source_cluster_ci95": boot_ci(clusters, rate_diff)},
            "leave_one_source_out_share_difference": {"min": min(x[1] for x in loso) if loso else None,
                                                      "max": max(x[1] for x in loso) if loso else None,
                                                      "max_fisher_p": max(x[2] for x in loso) if loso else None},
            "n_sources": len(clusters)}


def rates(cases, src, aud):
    out = {}
    for m, a in aud.items():
        by = defaultdict(lambda: [0, 0, 0])
        for k in cases:
            r = a.get(k)
            b = by[src[k[0]]]
            b[2] += 1
            if r and r["category"] in WRONG_CATS:
                b[0] += 1
                b[1] += r["category"] == "supported_inapplicable"
        cl = list(by.values())
        wrong, si, n = (sum(c[i] for c in cl) for i in range(3))
        out[m] = {"cases": n, "wrong": wrong, "wrong_rate_wilson": wilson(wrong, n),
                  "wrong_rate_source_ci95": boot_ci(cl, lambda x: sum(c[0] for c in x) / sum(c[2] for c in x)),
                  "si": si, "si_rate_wilson": wilson(si, n),
                  "si_rate_source_ci95": boot_ci(cl, lambda x: sum(c[1] for c in x) / sum(c[2] for c in x))}
    return out


def verifiers(set_name, src, cases):
    out = {}
    for m in ALL:
        try:
            R.use_set(set_name, m)
            arms = R.load(R.default_split())
        except Exception:
            continue
        ok0 = {(it["id"], c["label"]): c["gold"]["answer_correct"] for it in R.ITEMS for c in it["cases"]}
        n_all = len(cases)
        res = {"answered": len(ok0), "all_cases": n_all,
               "no_verifier": {"answered_accuracy": f"{sum(ok0.values())}/{len(ok0)}", "end_to_end_accuracy": f"{sum(ok0.values())}/{n_all}"}}
        for arm in ("rules", "judge", "judge_checklist", "qbr-judge_only", "qbr-source_bound"):
            rows = arms.get(arm)
            if not rows:
                continue
            fin = {(r["item"], r["label"]): R._final_ok(r) for r in rows}
            if set(fin) != set(ok0):
                res[arm] = {"incomplete": f"{len(fin)}/{len(ok0)}"}
                continue
            fixed = sum(fin[k] and not ok0[k] for k in ok0)
            broken = sum(ok0[k] and not fin[k] for k in ok0)
            by = defaultdict(lambda: [0, 0])
            for k in ok0:
                by[src[k[0]]][0] += int(fin[k]) - int(ok0[k])
                by[src[k[0]]][1] += 1
            cl = list(by.values())
            d = {"answered_accuracy": f"{sum(fin.values())}/{len(fin)}", "end_to_end_accuracy": f"{sum(fin.values())}/{n_all}",
                 "fixed": fixed, "broken": broken,
                 "accuracy_difference_vs_none": round((fixed - broken) / len(ok0), 3),
                 "difference_source_cluster_ci95": boot_ci(cl, lambda x: sum(c[0] for c in x) / sum(c[1] for c in x))}
            if arm == "qbr-source_bound":
                cert = [r for r in rows if (r.get("trace") or {}).get("used") == "code"]
                k_ok = sum(R._final_ok(r) for r in cert)
                j = {(r["item"], r["label"]): R._final_ok(r) for r in arms["qbr-judge_only"]}
                d["certificate"] = {"coverage": f"{len(cert)}/{len(rows)}", "precision": f"{k_ok}/{len(cert)}",
                                    "precision_exact_ci95": clopper_pearson(k_ok, len(cert)) if cert else None,
                                    "vs_judge_only_fixed": sum(fin[k] and not j[k] for k in fin),
                                    "vs_judge_only_broken": sum(j[k] and not fin[k] for k in fin)}
            res[arm] = d
        out[m] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="replication", choices=["discovery", "replication"])
    s = ap.parse_args().set
    items, src, cases, aud = load(s)
    out = {"set": s, "unit_of_resampling": "source document", "rates": rates(cases, src, aud)}
    if all(m in aud for m in STRONG + WEAK):
        out["H1"] = h1_block(cases, src, aud)
        contested = {k for a in aud.values() for k, r in a.items() if r.get("gold_contestable")}
        flagged_items = {k[0] for a in aud.values() for k, r in a.items() if r.get("template_ambiguity")}
        excl = frozenset(contested | {k for k in cases if k[0] in flagged_items})
        out["H1_excluding_contested_and_template_items"] = dict(h1_block(cases, src, aud, excl),
                                                                excluded_cases=len(excl), excluded_items=sorted(flagged_items))
    out["verifiers"] = verifiers(s, src, cases)
    (RES / s / "statistics.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1)[:4000])


if __name__ == "__main__":
    main()
