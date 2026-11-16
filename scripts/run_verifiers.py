"""Run verifiers on a frozen set (resumable) and score them. Usage:
    python scripts/run_verifiers.py --set contrast --split test --arms rules,judge,judge_checklist,dcv,qbr
    python scripts/run_verifiers.py --set heldout --arms rules,judge_checklist,qbr
    python scripts/run_verifiers.py --set replication --assistant qwen3-4b --arms rules,judge,judge_checklist,qbr
    add --score to recompute the summary from the logged outputs (no model calls)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from applicability import ARMS  # noqa: E402

DATA, RES = ROOT / "data", ROOT / "results"
# set -> (items file, results folder, split label stored in the frozen items; None: dev/test split named in the file names)
SETS = {"contrast": ("contrast/items.jsonl", "contrast", None),
        "contrast_long": ("contrast/items_long.jsonl", "contrast_long", None),
        "heldout": ("heldout/items.jsonl", "heldout", "v2"),
        "discovery": ("discovery/items.jsonl", "discovery", "v3"),
        "replication": ("replication/items.jsonl", "replication", "v4")}
ITEMS, OUT, SPLIT = [], RES, None


def use_set(name, assistant=None):
    """Natural-answer sets are verified per assistant: data/<set>/answered/<assistant>.jsonl -> results/<set>/verifiers/<assistant>/."""
    global ITEMS, OUT, SPLIT
    items, out, SPLIT = SETS[name]
    if assistant:
        items, out = f"{name}/answered/{assistant}.jsonl", f"{name}/verifiers/{assistant}"
    ITEMS = [json.loads(l) for l in open(DATA / items, encoding="utf-8")]
    OUT = RES / out


def default_split():
    return SPLIT or "test"


def _stem(split, arm):
    return arm if SPLIT else f"{split}_{arm}"


use_set("contrast")


def run(split, arms):
    OUT.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        path, raw_path = OUT / f"{_stem(split, arm)}.jsonl", OUT / f"{_stem(split, arm)}_raw.jsonl"
        done = {(r["item"], r["label"]) for r in map(json.loads, open(path, encoding="utf-8"))} if path.exists() else set()
        cache = {}
        for item in (i for i in ITEMS if i["split"] == split):
            for case in item["cases"]:
                if (item["id"], case["label"]) in done:
                    continue
                try:
                    res = ARMS[arm](item, case, cache)
                except Exception as exc:  # keep the failure, never invent a verdict
                    res = {"verdict": "error", "corrected": repr(exc)[:300], "calls": []}
                row = {"item": item["id"], "label": case["label"], "domain": item["domain"], "family": item["family"],
                       "verdict": res["verdict"], "corrected": res["corrected"], "gold": case["gold"],
                       "n_calls": len(res["calls"]), "seconds": round(sum(c["seconds"] for c in res["calls"]), 2),
                       "trace": res.get("trace"), "raw": res.get("raw")}
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                with open(raw_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"item": item["id"], "label": case["label"], "calls": res["calls"]}, ensure_ascii=False) + "\n")
                print(arm, item["id"], case["label"], res["verdict"], "gold_ok" if case["gold"]["answer_correct"] else "gold_wrong", flush=True)


def _final_ok(r):
    """Is the decision the user ends up with right? keep (correct) / flip (incorrect) / defer (insufficient)."""
    g, v = r["gold"], r["verdict"]
    if r.get("arm") == "direct":
        return v == "correct"
    if g["answer_correct"]:
        return v == "correct"
    if r["family"] == "population_scope":
        return v in ("insufficient", "incorrect")
    return v == "incorrect"


def _wilson(k, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** .5) / d
    return (round(c - h, 3), round(c + h, 3))


def _mcnemar(b, c):
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


ABLATIONS = {"dcv-no_counterfactual": {"counterfactual": False}, "dcv-no_selection": {"selection": False},
             "dcv-no_arithmetic": {"arithmetic": False}, "dcv-no_abstention": {"abstention": False}}


def load(split):
    from applicability import decide, qbr_decide
    cases = {(i["id"], c["label"]): c for i in ITEMS for c in i["cases"]}
    arms = {}
    for path in sorted(OUT.glob("*.jsonl" if SPLIT else f"{split}_*.jsonl")):
        if path.stem.endswith("_raw"):
            continue
        arm = path.stem if SPLIT else path.stem[len(split) + 1:]
        arms[arm] = [dict(json.loads(l), arm=arm) for l in open(path, encoding="utf-8")]
    if "dcv" in arms:
        for name, flags in ABLATIONS.items():
            rows = []
            for r in arms["dcv"]:
                t = r.get("trace")
                v = decide(t["source"], t["user"], cases[(r["item"], r["label"])]["answer"], **flags)["verdict"] if t else r["verdict"]
                rows.append(dict(r, arm=name, verdict=v, n_calls=r["n_calls"], seconds=r["seconds"]))
            arms[name] = rows
    if "qbr" in arms:
        items = {i["id"]: i for i in ITEMS}
        for policy in ("bound_first", "agree", "judge_only", "source_bound"):  # recomputed from the logged model output with the current binding code
            rows = []
            for r in arms["qbr"]:
                res = qbr_decide(r["raw"], items[r["item"]], cases[(r["item"], r["label"])], policy) if r.get("raw") else {"verdict": r["verdict"], "trace": r.get("trace") or {}}
                rows.append(dict(r, arm="qbr" if policy == "bound_first" else f"qbr-{policy}", verdict=res["verdict"], trace=res["trace"]))
            arms["qbr" if policy == "bound_first" else f"qbr-{policy}"] = rows
    return arms


def _cluster_ci(rows, reps=4000, seed=7):
    """95% bootstrap interval for decision accuracy, resampling source items (cases of one item are not independent)."""
    import random
    by = defaultdict(list)
    for r in rows:
        by[r["item"]].append(_final_ok(r))
    keys = sorted(by)
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        pick = [by[rng.choice(keys)] for _ in keys]
        stats.append(sum(map(sum, pick)) / sum(map(len, pick)))
    stats.sort()
    return (round(stats[int(.025 * reps)], 3), round(stats[int(.975 * reps)], 3))


def score(split, quiet=False):
    arms = load(split)
    table = {}
    for arm, rows in arms.items():
        by = defaultdict(list)
        for r in rows:
            by[r["label"]].append(r)
        flagged = lambda r: r["verdict"] in ("incorrect", "insufficient")
        b, c, a = by["B"], by["C"], by["A"]
        ok = sum(map(_final_ok, rows))
        fam = defaultdict(lambda: [0, 0])
        for r in b:
            fam[r["family"]][0] += _final_ok(r)
            fam[r["family"]][1] += 1
        table[arm] = {
            "cases": len(rows), "errors": sum(r["verdict"] == "error" for r in rows),
            "decision_accuracy": f"{ok}/{len(rows)}", "decision_accuracy_ci95": _wilson(ok, len(rows)),
            "decision_accuracy_item_bootstrap_ci95": _cluster_ci(rows),
            "items_all_cases_right": f"{sum(all(_final_ok(x) for x in rows if x['item'] == it) for it in {x['item'] for x in rows})}/{len({x['item'] for x in rows})}",
            "B_wrong_answer_caught_and_fixed": f"{sum(map(_final_ok, b))}/{len(b)}",
            "B_flagged_any": f"{sum(map(flagged, b))}/{len(b)}",
            "C_kept_irrelevant_mismatch": f"{sum(r['verdict'] == 'correct' for r in c)}/{len(c)}",
            "A_false_alarm": f"{sum(map(flagged, a))}/{len(a)}",
            "defer_when_answer_right": sum(r["verdict"] == "insufficient" for r in a + c),
            "calls": sum(r["n_calls"] for r in rows), "seconds": round(sum(r["seconds"] for r in rows)),
            "B_fixed_by_family": {k: f"{v[0]}/{v[1]}" for k, v in sorted(fam.items())},
            "wrong_interventions_on_right_answers": sum(r["verdict"] == "incorrect" for r in a + c),
        }
        if arm.startswith("qbr"):
            strata = defaultdict(lambda: [0, 0])
            for r in rows:
                used = ((r.get("trace") or {}).get("used") or r["verdict"]).split(" (")[0]
                strata[used][0] += _final_ok(r)
                strata[used][1] += 1
            table[arm]["decided_by"] = {k: f"{v[0]}/{v[1]} right" for k, v in sorted(strata.items())}
            reasons = defaultdict(int)
            for r in rows:
                for why in ((r.get("trace") or {}).get("bind_reasons") or {}).values():
                    reasons[why] += 1
            table[arm]["unbound_operand_reasons"] = dict(reasons)
    for ref in ("dcv", "judge_checklist"):
        if ref not in arms:
            continue
        mine = {(r["item"], r["label"]): _final_ok(r) for r in arms[ref]}
        for arm, rows in arms.items():
            other = {(r["item"], r["label"]): _final_ok(r) for r in rows}
            keys = mine.keys() & other.keys()
            bb = sum(mine[k] and not other[k] for k in keys)
            cc = sum(other[k] and not mine[k] for k in keys)
            table[arm][f"vs_{ref}_paired"] = {f"{ref}_only_right": bb, "this_only_right": cc, "exact_mcnemar_p": round(_mcnemar(bb, cc), 4)}
    total = [c for i in ITEMS if i["split"] == split for c in i["cases"]]
    summary = {"split": split, "cases": len(total), "no_verifier_decision_accuracy": f"{sum(c['gold']['answer_correct'] for c in total)}/{len(total)}", "arms": table}
    if not quiet:
        print(json.dumps(summary, indent=1, ensure_ascii=False))
    (OUT / ("summary.json" if SPLIT else f"{split}_summary.json")).write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="contrast", choices=sorted(SETS))
    ap.add_argument("--assistant", help="natural-answer sets: whose answers to verify")
    ap.add_argument("--split", help="contrast sets: dev or test (default test)")
    ap.add_argument("--arms", default="rules,judge,judge_checklist,qbr")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    use_set(a.set, a.assistant)
    split = a.split or default_split()
    if a.score:
        score(split)
    else:
        run(split, a.arms.split(","))
