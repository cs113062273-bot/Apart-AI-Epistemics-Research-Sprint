"""Natural-answer analysis (no model calls) for the discovery set and the pre-registered replication.
    python scripts/analyze_natural.py --set discovery     ->  results/discovery/analysis.json
    python scripts/analyze_natural.py --set replication   ->  results/replication/analysis.json
Prevalence uses the pre-registered automatic typing over ALL cases; the per-case audit is reported separately.
Natural answers can be right in B and wrong in A, so verifier metrics come from answer correctness: wrong answers fixed,
right answers kept, decision accuracy (item-bootstrap CI), exact McNemar, certificate coverage/precision, and how many
audited supported-but-inapplicable errors each verifier corrected. H1 (replication pre-registration): one-sided Fisher exact test that
the supported-but-inapplicable share of wrong answers is larger for the two stronger assistants than for the two weaker ones.
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from math import comb, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_verifiers as R  # noqa: E402

DATA = ROOT / "data"
RES = ROOT / "results"
ASSISTANTS = ["qwen35-9b", "qwen3-4b", "qwen2.5-1.5b", "smollm2-1.7b"]
STRONG, WEAK = ("qwen35-9b", "qwen3-4b"), ("qwen2.5-1.5b", "smollm2-1.7b")
ARMS = ["rules", "judge", "judge_checklist", "qbr-judge_only", "qbr", "qbr-source_bound"]
WRONG_CATS = ("no_answer", "unfaithful_quote", "supported_inapplicable", "ambiguous_value", "other_printed_value", "numeric_or_reasoning_error")
SET = "discovery"


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def fisher_greater(a, b, c, d):
    """One-sided Fisher exact p for [[a, b], [c, d]]: P(X >= a) under the hypergeometric null."""
    n1, n2, k = a + b, c + d, a + c
    tot = comb(n1 + n2, k)
    return sum(comb(n1, x) * comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / tot


def boot(by_item, reps=4000, seed=7):
    keys = sorted(by_item)
    rng = random.Random(seed)
    st = []
    for _ in range(reps):
        draw = [by_item[rng.choice(keys)] for _ in keys]  # numerator and denominator from the same resampled items
        st.append(sum(map(sum, draw)) / sum(map(len, draw)))
    st.sort()
    return [round(st[int(.025 * reps)], 3), round(st[int(.975 * reps)], 3)]


def base_items():
    return [json.loads(l) for l in open(DATA / SET / "items.jsonl", encoding="utf-8")]


def prevalence(model):
    raw = DATA / SET / "answers" / f"{model}.jsonl"
    if not raw.exists() or not (DATA / SET / "answered" / f"{model}.jsonl").exists():
        return None
    import run_assistants as RN
    base = base_items()
    ans = {(r["item"], r["label"]): r for r in map(json.loads, open(raw, encoding="utf-8"))}
    by_label = defaultdict(Counter)
    for it in base:
        for c in it["cases"]:
            out_ = (ans.get((it["id"], c["label"])) or {}).get("out")
            kind = "no_answer" if not out_ else RN.type_error(it, c, out_, out_["decision"] == c["truth"])[0]
            by_label[c["label"]][kind] += 1
    out = {"cases_total": sum(len(i["cases"]) for i in base),
           "cases_answered": sum(1 for it in base for c in it["cases"] if (ans.get((it["id"], c["label"])) or {}).get("out"))}
    for lab in "ABC":
        t = by_label[lab]
        n = sum(t.values())
        wrong = n - t["correct"] - t["correct_with_trap_value"]
        out[lab] = {"n": n, "wrong": wrong, "wrong_rate_ci95": wilson(wrong, n), "types": dict(t),
                    "supported_inapplicable": t["supported_inapplicable"], "supported_inapplicable_ci95": wilson(t["supported_inapplicable"], n)}
    allc = sum((by_label[l] for l in "ABC"), Counter())
    out["all"] = {"n": sum(allc.values()), "wrong": sum(allc.values()) - allc["correct"] - allc["correct_with_trap_value"], "types": dict(allc)}
    return out


def audit_rows(model):
    p = RES / SET / "audit" / f"{model}.json"
    return {(r["item"], r["label"]): r for r in json.loads(p.read_text(encoding="utf-8"))} if p.exists() else None


def audit(model):
    sheet_p = RES / SET / "audit" / "sheets" / f"{model}.json"
    aud = audit_rows(model)
    if not (sheet_p.exists() and aud):
        return None
    sheet = {(r["item"], r["label"]): r for r in json.loads(sheet_p.read_text(encoding="utf-8"))}
    assert set(sheet) == set(aud), (model, sorted(set(sheet) ^ set(aud)))
    base = base_items()
    n = {lab: sum(1 for it in base for c in it["cases"] if c["label"] == lab) for lab in "ABC"}
    by = {lab: Counter() for lab in "ABC"}
    for (i, lab), r in aud.items():
        by[lab][r["category"]] += 1
    tot = sum(by.values(), Counter())
    return {"n_per_label": n, "by_label": {lab: dict(c) for lab, c in by.items()}, "totals": dict(tot),
            "wrong_total": sum(tot[c] for c in WRONG_CATS),
            "B_supported_inapplicable": f"{by['B']['supported_inapplicable']}/{n['B']}",
            "B_supported_inapplicable_or_ambiguous": f"{by['B']['supported_inapplicable'] + by['B']['ambiguous_value']}/{n['B']}",
            "B_wrong": f"{sum(by['B'][c] for c in WRONG_CATS)}/{n['B']}",
            "gold_contestable": [list(k) for k, r in aud.items() if r.get("gold_contestable")]}


def verifiers(model):
    try:
        R.use_set(SET, model)
        arms = R.load(R.default_split())
    except Exception:
        return None
    arms = {k: v for k, v in arms.items() if k in ARMS}
    if not arms:
        return None
    ok0 = {(it["id"], c["label"]): c["gold"]["answer_correct"] for it in R.ITEMS for c in it["cases"]}  # answered cases
    aud = audit_rows(model) or {}
    si = [k for k, r in aud.items() if r["category"] == "supported_inapplicable" and k in ok0]
    res = {"no_verifier": {"decision_accuracy": f"{sum(ok0.values())}/{len(ok0)}"}}
    by0 = defaultdict(list)
    for (i, _), v in ok0.items():
        by0[i].append(int(v))
    res["no_verifier"]["ci95"] = boot(by0)
    finals = {}
    for arm, rows in arms.items():
        fin = {(r["item"], r["label"]): R._final_ok(r) for r in rows}
        if set(fin) != set(ok0):
            res[arm] = {"incomplete": f"{len(fin)}/{len(ok0)}"}
            continue
        finals[arm] = fin
        wrong = [k for k, v in ok0.items() if not v]
        right = [k for k, v in ok0.items() if v]
        by = defaultdict(list)
        for (i, _), v in fin.items():
            by[i].append(int(v))
        d = {"decision_accuracy": f"{sum(fin.values())}/{len(fin)}", "ci95": boot(by),
             "wrong_fixed": f"{sum(fin[k] for k in wrong)}/{len(wrong)}", "right_kept": f"{sum(fin[k] for k in right)}/{len(right)}",
             "si_fixed": f"{sum(fin[k] for k in si)}/{len(si)}", "errors": sum(r["verdict"] == "error" for r in rows)}
        if arm.startswith("qbr") and arm != "qbr-judge_only":
            cert = [r for r in rows if (r.get("trace") or {}).get("used") == "code"]
            d["certified"] = f"{sum(R._final_ok(r) for r in cert)}/{len(cert)}"
            d["decided_by"] = dict(Counter((r.get("trace") or {}).get("used", "error") for r in rows))
        res[arm] = d
    pairs = []
    for x, y in (("qbr-source_bound", "judge_checklist"), ("qbr-source_bound", "qbr-judge_only"), ("judge_checklist", "judge"),
                 ("judge_checklist", "rules")):
        if x in finals and y in finals:
            b = sum(finals[x][k] and not finals[y][k] for k in finals[x])
            c = sum(finals[y][k] and not finals[x][k] for k in finals[x])
            pairs.append({"x": x, "y": y, "x_only": b, "y_only": c, "p": round(mcnemar(b, c), 4)})
    res["paired"] = pairs
    return res


def h1(out):
    if not all(out[m]["audit"] for m in STRONG + WEAK):
        return None
    s_si = sum(out[m]["audit"]["totals"].get("supported_inapplicable", 0) for m in STRONG)
    s_w = sum(out[m]["audit"]["wrong_total"] for m in STRONG)
    w_si = sum(out[m]["audit"]["totals"].get("supported_inapplicable", 0) for m in WEAK)
    w_w = sum(out[m]["audit"]["wrong_total"] for m in WEAK)
    return {"strong_si_of_wrong": f"{s_si}/{s_w}", "weak_si_of_wrong": f"{w_si}/{w_w}",
            "fisher_one_sided_p": round(fisher_greater(s_si, s_w - s_si, w_si, w_w - w_si), 4)}


def h1_sensitivity(out):
    """Sensitivity (not pre-registered): H1 after removing every item that any audit flags as template-ambiguous,
    for all assistants alike. The pre-registered H1 above uses every item."""
    flagged = set()
    for m in STRONG + WEAK:
        for (i, lab), r in (audit_rows(m) or {}).items():
            if r.get("template_ambiguity"):
                flagged.add(i)
    if not flagged or not all(out[m]["audit"] for m in STRONG + WEAK):
        return None
    def counts(models):
        si = w = 0
        for m in models:
            for (i, lab), r in audit_rows(m).items():
                if i in flagged:
                    continue
                if r["category"] in WRONG_CATS:
                    w += 1
                    si += r["category"] == "supported_inapplicable"
        return si, w
    s_si, s_w = counts(STRONG)
    w_si, w_w = counts(WEAK)
    return {"excluded_items": sorted(flagged), "strong_si_of_wrong": f"{s_si}/{s_w}", "weak_si_of_wrong": f"{w_si}/{w_w}",
            "fisher_one_sided_p": round(fisher_greater(s_si, s_w - s_si, w_si, w_w - w_si), 4)}


def by_family():
    """Audited supported-but-inapplicable errors per condition family and assistant, with the number of cases per family
    (descriptive; shows which printed conditions defeat assistants)."""
    fam = {it["id"]: it["family"] for it in base_items()}
    n_cases = Counter(fam[it["id"]] for it in base_items() for _ in it["cases"])
    table = defaultdict(dict)
    cases_hit = defaultdict(set)
    for m in ASSISTANTS:
        aud = audit_rows(m)
        if not aud:
            continue
        for (i, lab), r in aud.items():
            if r["category"] == "supported_inapplicable":
                table[fam[i]][m] = table[fam[i]].get(m, 0) + 1
                cases_hit[fam[i]].add((i, lab))
    return {f: {"cases": n_cases[f], "by_assistant": table.get(f, {}), "distinct_cases": len(cases_hit.get(f, ()))} for f in sorted(n_cases)}


def main():
    global SET
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="discovery", choices=["discovery", "replication"])
    SET = ap.parse_args().set
    out = {m: {"prevalence": prevalence(m), "audit": audit(m), "verifiers": verifiers(m)} for m in ASSISTANTS}
    out["H1"] = h1(out)
    out["by_family"] = by_family()
    out["H1_sensitivity"] = h1_sensitivity(out)
    (RES / SET / "analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({m: (v.get("audit") or {}).get("totals") if isinstance(v, dict) and "audit" in v else v for m, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
