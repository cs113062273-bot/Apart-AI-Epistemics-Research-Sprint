"""Audit sheet for natural answers (separate from the pre-registered automatic typing, which stays unchanged).
    python scripts/make_audit_sheet.py --set replication --model qwen3-4b   ->  results/replication/audit/sheets/qwen3-4b.json
Lists every case whose answer is wrong, missing, or right while citing the trap value, with automatic sub-checks:
  quote_verbatim      the whole quote (normalized) occurs in the excerpt
  quote_numbers_in_source  every number in the quote is printed in the excerpt
  cites_trap / cites_applicable  the explanation or quote mentions the trap / applicable value
Audit categories are then assigned case by case in results/<set>/audit/<model>.json (field 'category', with a reason):
  supported_inapplicable | ambiguous_value | other_printed_value | numeric_or_reasoning_error | unfaithful_quote | no_answer
  | right_with_inapplicable_value | right_for_wrong_reason; flags gold_contestable and template_ambiguity
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_assistants as RN  # noqa: E402

DATA = ROOT / "data"


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", required=True, choices=["discovery", "replication"])
    a = ap.parse_args()
    base = [json.loads(l) for l in open(DATA / a.set / "items.jsonl", encoding="utf-8")]
    ans = {(r["item"], r["label"]): r for r in map(json.loads, open(DATA / a.set / "answers" / f"{a.model}.jsonl", encoding="utf-8"))}
    sheet = []
    for it in base:
        ex_nums = RN.numbers(it["excerpt"])
        for c in it["cases"]:
            out = (ans.get((it["id"], c["label"])) or {}).get("out")
            row = {"item": it["id"], "label": c["label"], "family": it["family"], "context": c["context"], "truth": c["truth"],
                   "applicable_text": c["applicable_text"], "trap_text": c["trap_text"]}
            if not out:
                sheet.append(dict(row, decision=None, auto_type="no_answer"))
                continue
            correct = out["decision"] == c["truth"]
            kind, info = RN.type_error(it, c, out, correct)
            if correct and kind != "correct_with_trap_value":
                continue
            qn = RN.numbers(out["quote"])
            sheet.append(dict(row, decision=out["decision"], auto_type=kind, explanation=out["explanation"], quote=out["quote"],
                              quote_verbatim=bool(out["quote"].strip()) and norm(out["quote"]) in norm(it["excerpt"]),
                              quote_numbers_in_source=all(any(abs(q - e) < 1e-6 for e in ex_nums) for q in qn),
                              cites_trap=info["used_trap"], cites_applicable=info["used_applicable"]))
    p = ROOT / "results" / a.set / "audit" / "sheets" / f"{a.model}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(sheet), "cases to audit ->", p)


if __name__ == "__main__":
    main()
