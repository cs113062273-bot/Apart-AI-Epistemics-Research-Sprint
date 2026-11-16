"""Post-hoc diagnostic of QBR's logged outputs (no model calls, no change to the frozen method or its verdicts).
Separates four properties that 'verified' could mean, per case:
  traceable   every operand the computation uses has a quote found in its source/user text that prints its value (binding checks)
  compatible  ...and the printed condition is compatible with the user's situation (lexicon check, per-unit scaling, limit from user)
  uses_source the expression the code evaluates contains at least one operand taken from the source  (NOT checked by QBR)
  correct     the final decision is right
Also splits held-out items by whether their condition family occurs in the contrast set.
    python scripts/qbr_certificates.py   ->  results/qbr_certificates.json
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_verifiers as R  # noqa: E402
from applicability import _bound  # noqa: E402


def names(expr):
    try:
        return {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}
    except SyntaxError:
        return None


def study(set_name, split):
    R.use_set(set_name)
    items = {i["id"]: i for i in R.ITEMS}
    cases = {(i["id"], c["label"]): c for i in R.ITEMS for c in i["cases"]}
    loaded = R.load(split)
    rows = loaded["qbr"]
    judge_only = {(r["item"], r["label"]): r for r in loaded["qbr-judge_only"]}
    out = {"cases": len(rows), "structured_output": 0, "all_used_traceable": 0, "all_used_traceable_and_compatible": 0,
           "certified": 0, "certified_uses_source": 0, "certified_correct": 0, "certified_uses_source_correct": 0,
           "certified_without_source": [], "source_rule_accuracy": 0}
    # post hoc: the missing rule (a certified expression must use a source operand), else the judge verdict from the same call
    for r in rows:
        raw, used = r.get("raw"), (r.get("trace") or {}).get("used")
        keep = r
        if raw and used == "code":
            ops = {o["name"]: o for o in raw["operands"]}
            if not any(ops[k]["from"] == "source" for k in (names(raw["user_value_expression"]) or set()) if k in ops):
                keep = judge_only[(r["item"], r["label"])]
        out["source_rule_accuracy"] += R._final_ok(keep)
    for r in rows:
        raw = r.get("raw")
        if not raw:
            continue
        out["structured_output"] += 1
        it, case = items[r["item"]], cases[(r["item"], r["label"])]
        ops = {o["name"]: o for o in raw["operands"]}
        used = (names(raw["user_value_expression"]) or set(ops)) | {raw["limit_operand"]}
        used_ops = [ops[k] for k in used if k in ops]
        traceable = bool(used_ops) and all(not _bound(o, it["excerpt"], case["context"]) for o in used_ops)
        reasons = (r.get("trace") or {}).get("bind_reasons", {})
        if traceable:
            out["all_used_traceable"] += 1
        if (r.get("trace") or {}).get("used") == "code":
            out["all_used_traceable_and_compatible"] += 1
        elif traceable and not reasons:
            pass
        if (r.get("trace") or {}).get("used") != "code":
            continue
        ok = R._final_ok(r)
        src = any(ops[k]["from"] == "source" for k in (names(raw["user_value_expression"]) or set()) if k in ops)
        out["certified"] += 1
        out["certified_correct"] += ok
        out["certified_uses_source"] += src
        out["certified_uses_source_correct"] += ok and src
        if not src:
            out["certified_without_source"].append({"item": r["item"], "label": r["label"], "expression": raw["user_value_expression"],
                                                    "limit": raw["limit_operand"], "correct": ok})
    return out


def seen_split():
    R.use_set("contrast")
    v1_fams = {i["family"] for i in R.ITEMS}
    R.use_set("heldout")
    fam = {i["id"]: i["family"] for i in R.ITEMS}
    arms = R.load(R.default_split())
    res = {}
    for arm in ("judge_checklist", "qbr", "qbr-judge_only", "judge", "rules", "dcv"):
        if arm not in arms:
            continue
        seen = [R._final_ok(r) for r in arms[arm] if fam[r["item"]] in v1_fams]
        new = [R._final_ok(r) for r in arms[arm] if fam[r["item"]] not in v1_fams]
        res[arm] = {"seen_type": f"{sum(seen)}/{len(seen)}", "new_type": f"{sum(new)}/{len(new)}"}
    nv = [c["label"] != "B" for i in R.ITEMS for c in i["cases"] if i["family"] in v1_fams]
    nn = [c["label"] != "B" for i in R.ITEMS for c in i["cases"] if i["family"] not in v1_fams]
    res["no_verifier"] = {"seen_type": f"{sum(nv)}/{len(nv)}", "new_type": f"{sum(nn)}/{len(nn)}"}
    res["seen_type_items"] = sorted(i for i, f in fam.items() if f in v1_fams)
    return res


def main():
    out = {"contrast_test": study("contrast", "test"), "heldout": study("heldout", R.SETS["heldout"][2]),
           "heldout_seen_vs_new_condition_type": seen_split()}
    (ROOT / "results/qbr_certificates.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
