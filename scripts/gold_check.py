"""Gold-label validity, checked separately from error types (no model calls).
    python scripts/gold_check.py  ->  results/gold_check.json
For every natural-answer case (discovery and replication): recompute the gold decision from the printed applicable value, the user's limit and direction, and check it
matches the frozen label; check that the applicable and trap snippets are printed verbatim in the excerpt; list every case flagged in
any audit as gold-contestable or template-ambiguous (these flags come from reading the case, never from a model's answer)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RES = ROOT / "results"


def main():
    out = {}
    for s in ("discovery", "replication"):
        items = [json.loads(l) for l in open(DATA / s / "items.jsonl", encoding="utf-8")]
        mismatches, missing = [], []
        for it in items:
            for c in it["cases"]:
                ok = c["value"] >= c["limit"] - 1e-9 if c["direction"] == "at least" else c["value"] <= c["limit"] + 1e-9
                if (it["decision_options"][0] if ok else it["decision_options"][1]) != c["truth"]:
                    mismatches.append((it["id"], c["label"]))
                for t in (c["applicable_text"], c["trap_text"]):
                    if t not in it["excerpt"]:
                        missing.append((it["id"], c["label"], t))
        flags = {"gold_contestable": set(), "template_ambiguity": set()}
        for p in (RES / s / "audit").glob("*.json"):
            for r in json.loads(p.read_text(encoding="utf-8")):
                for f in flags:
                    if r.get(f):
                        flags[f].add((r["item"], r["label"]))
        flagged_items = sorted({i for i, _ in flags["template_ambiguity"]})
        out[s] = {"cases": sum(len(i["cases"]) for i in items), "recomputed_gold_mismatches": mismatches, "snippets_not_printed": missing,
                  "gold_contestable_cases": sorted(map(list, flags["gold_contestable"])),
                  "template_ambiguous_cases": sorted(map(list, flags["template_ambiguity"])),
                  "template_ambiguous_items": flagged_items,
                  "cases_in_template_ambiguous_items": sum(len(i["cases"]) for i in items if i["id"] in flagged_items)}
    (RES / "gold_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
