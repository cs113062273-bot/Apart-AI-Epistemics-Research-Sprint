"""Item-level analysis of a scored study (no model calls).
    python scripts/item_analysis.py --set heldout            ->  results/heldout/item_analysis.json
    python scripts/item_analysis.py --set contrast --split test  ->  results/contrast/test_item_analysis.json
Writes
  per-item cases right for each arm, item-bootstrap CI of paired differences, and the QBR increment over its own judge verdict.
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_verifiers as R  # noqa: E402

ARMS = ["rules", "judge", "judge_checklist", "dcv", "direct", "qbr", "qbr-judge_only", "qbr-agree", "nli_claim", "nli_answer", "lynx"]


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def paired(arms, x, y, reps=4000, seed=7):
    ok = {a: {(r["item"], r["label"]): R._final_ok(r) for r in arms[a]} for a in (x, y)}
    keys = sorted(ok[x])
    xo = sum(ok[x][k] and not ok[y][k] for k in keys)
    yo = sum(ok[y][k] and not ok[x][k] for k in keys)
    by = defaultdict(list)
    for k in keys:
        by[k[0]].append(ok[x][k] - ok[y][k])
    items = sorted(by)
    rng = random.Random(seed)
    stats = sorted(sum(sum(by[rng.choice(items)]) for _ in items) / len(keys) for _ in range(reps))
    return {"x": x, "y": y, "x_only_right": xo, "y_only_right": yo, "exact_mcnemar_p": round(mcnemar(xo, yo), 4),
            "diff": round((xo - yo) / len(keys), 3),
            "diff_item_bootstrap_ci95": [round(stats[int(.025 * reps)], 3), round(stats[int(.975 * reps)], 3)],
            "items_x_better": sum(sum(v) > 0 for v in by.values()), "items_y_better": sum(sum(v) < 0 for v in by.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="heldout", choices=sorted(R.SETS))
    ap.add_argument("--split", help="contrast sets: dev or test (default test)")
    a = ap.parse_args()
    R.use_set(a.set)
    a.split = a.split or R.default_split()
    arms = R.load(a.split)
    arms = {k: v for k, v in arms.items() if k in ARMS}
    items = [i for i in R.ITEMS if i["split"] == a.split]
    per_item = {}
    for i in items:
        row = {"family": i["family"]}
        for arm, rs in arms.items():
            mine = sorted((r for r in rs if r["item"] == i["id"]), key=lambda r: r["label"])
            row[arm] = "".join(r["label"] if R._final_ok(r) else "." for r in mine)
        per_item[i["id"]] = row
    code_rows = [dict(item=r["item"], label=r["label"], verdict=r["verdict"], ok=R._final_ok(r))
                 for r in arms.get("qbr", []) if (r.get("trace") or {}).get("used") == "code"]
    out = {"per_item_cases_right": per_item,
           "qbr_code_tier_cases": code_rows,
           "paired": [paired(arms, x, y) for x, y in (("qbr", "judge_checklist"), ("qbr", "qbr-judge_only"), ("qbr-judge_only", "judge_checklist"),
                                                       ("judge_checklist", "judge"), ("qbr", "dcv")) if x in arms and y in arms],
           "no_verifier_per_item": {i["id"]: "".join("." if c["label"] == "B" else c["label"] for c in sorted(i["cases"], key=lambda c: c["label"])) for i in items}}
    path = R.OUT / ("item_analysis.json" if R.SPLIT else f"{a.split}_item_analysis.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, v in per_item.items():
        print(f"{k:26s}", " ".join(f"{arm}={v[arm]}" for arm in arms))
    print(json.dumps(out["paired"], indent=1))
    print(json.dumps(code_rows, indent=1))


if __name__ == "__main__":
    main()
