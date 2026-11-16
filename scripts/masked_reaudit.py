"""Masked re-audit of natural-answer error types by the same auditor.
    python scripts/masked_reaudit.py make     ->  results/masked_reaudit/sheet.json  (+ key.json)
    (labels written blind into results/masked_reaudit/labels.json as {"rid": category, ...})
    python scripts/masked_reaudit.py compare  ->  results/masked_reaudit/summary.json
Sample: every case first audited as supported_inapplicable, ambiguous_value or right-for-wrong-reason, plus an equal number of
other audited cases drawn with seed 20261116. Rows are shuffled; the sheet hides the set, the assistant, the automatic type and the
first label, and shows only what a label needs: situation, the two printed values with their conditions, gold, decision,
explanation and quote."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "masked_reaudit"
CORE = {"supported_inapplicable", "ambiguous_value", "right_with_inapplicable_value", "right_for_wrong_reason"}
SHOW = ("context", "applicable_text", "trap_text", "truth", "decision", "explanation", "quote")


def audited():
    rows = []
    for s in ("discovery", "replication"):
        for p in sorted((RES / s / "audit").glob("*.json")):
            model = p.stem
            sheet = {(r["item"], r["label"]): r for r in json.loads((RES / s / "audit" / "sheets" / f"{model}.json").read_text(encoding="utf-8"))}
            for r in json.loads(p.read_text(encoding="utf-8")):
                rows.append({"set": s, "model": model, "item": r["item"], "label": r["label"], "first": r["category"],
                             "sheet": sheet[(r["item"], r["label"])]})
    return rows


def make():
    rows = audited()
    rng = random.Random(20261116)
    core = [r for r in rows if r["first"] in CORE]
    rest = [r for r in rows if r["first"] not in CORE and r["first"] != "no_answer"]
    picked = core + rng.sample(rest, min(len(core), len(rest)))
    rng.shuffle(picked)
    sheet, key = [], {}
    for n, r in enumerate(picked, 1):
        rid = f"r{n:03d}"
        sheet.append({"rid": rid, **{k: r["sheet"].get(k) for k in SHOW}})
        key[rid] = {k: r[k] for k in ("set", "model", "item", "label", "first")}
    (OUT / "sheet.json").write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(len(sheet), "rows:", len(core), "core +", len(sheet) - len(core), "others")


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    cats = {c for p in pairs for c in p}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def compare():
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    lab = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    assert set(lab) == set(key), "labels must cover exactly the sheet"
    norm = lambda c: "right_wrong_reason" if c in ("right_with_inapplicable_value", "right_for_wrong_reason") else c  # noqa: E731
    pairs = [(norm(key[r]["first"]), norm(lab[r])) for r in key]
    si = [(a == "supported_inapplicable", b == "supported_inapplicable") for a, b in pairs]
    out = {"rows": len(pairs), "exact_agreement": sum(a == b for a, b in pairs), "kappa_all_categories": round(kappa(pairs), 3),
           "si_vs_rest": {"both_si": sum(a and b for a, b in si), "first_only": sum(a and not b for a, b in si),
                          "second_only": sum(b and not a for a, b in si), "neither": sum(not a and not b for a, b in si),
                          "kappa": round(kappa(si), 3)},
           "disagreements": [{"rid": r, **key[r], "second": lab[r]} for r in key if norm(key[r]["first"]) != norm(lab[r])]}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"make": make, "compare": compare}[sys.argv[1]]()
