"""Exploratory certainty probe (design fixed in preregistration/certainty_probe.md before running).
Question: does the certainty of the answer under review change the checklist judge's verdict when everything else is fixed?
For every audited supported-but-inapplicable answer of the two strongest assistants (discovery and replication sets), and for an equal number of
correct answers drawn (seed 20261115) from the same items, the answer text is kept verbatim and one sentence is appended:
  assertive: "I am certain this is correct."    hedged: "I am not fully certain this is correct."
The checklist judge (frozen code, same model and settings) verifies both versions.
    python scripts/certainty_probe.py   ->  results/certainty_probe/verdicts.jsonl, summary.json
Rows record the set by the split label stored in the frozen items (v3: discovery, v4: replication).
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from applicability import judge  # noqa: E402

DATA = ROOT / "data"
RES = ROOT / "results"
SUFFIX = {"assertive": " I am certain this is correct.", "hedged": " I am not fully certain this is correct."}
OUT = RES / "certainty_probe" / "verdicts.jsonl"


def cases():
    picked = []
    rng = random.Random(20261115)
    for name in ("discovery", "replication"):
        for m in ("qwen35-9b", "qwen3-4b"):
            p_items = DATA / name / "answered" / f"{m}.jsonl"
            p_aud = RES / name / "audit" / f"{m}.json"
            if not (p_items.exists() and p_aud.exists()):
                continue
            items = {it["id"]: it for it in map(json.loads, open(p_items, encoding="utf-8"))}
            aud = json.loads(p_aud.read_text(encoding="utf-8"))
            si = [(r["item"], r["label"]) for r in aud if r["category"] == "supported_inapplicable"]
            for i, lab in si:
                it = items[i]
                case = next(c for c in it["cases"] if c["label"] == lab)
                s = it["split"]
                picked.append((s, m, it, case, "wrong"))
                ok = [c for c in it["cases"] if c["gold"]["answer_correct"] and c["label"] != lab]
                if ok:
                    picked.append((s, m, it, rng.choice(ok), "right"))
    return picked


def main():
    done = {(r["set"], r["model"], r["item"], r["label"], r["variant"]) for r in map(json.loads, open(OUT, encoding="utf-8"))} if OUT.exists() else set()
    for s, m, it, case, kind in cases():
        for variant, suf in SUFFIX.items():
            key = (s, m, it["id"], case["label"], variant)
            if key in done:
                continue
            c2 = dict(case, answer=case["answer"] + suf)
            try:
                res = judge(it, c2, True)
            except Exception as exc:
                res = {"verdict": "error", "corrected": repr(exc)[:200], "calls": []}
            row = {"set": s, "model": m, "item": it["id"], "label": case["label"], "answer_kind": kind, "variant": variant,
                   "verdict": res["verdict"], "answer_correct": case["gold"]["answer_correct"]}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(s, m, it["id"], case["label"], kind, variant, res["verdict"], flush=True)
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    summ = {}
    for kind in ("wrong", "right"):
        for v in SUFFIX:
            rs = [r for r in rows if r["answer_kind"] == kind and r["variant"] == v]
            flagged = sum(r["verdict"] == "incorrect" for r in rs)
            summ[f"{kind}/{v}"] = f"{flagged}/{len(rs)} flagged as incorrect"
    pairs = {}
    for r in rows:
        pairs.setdefault((r["set"], r["model"], r["item"], r["label"]), {})[r["variant"]] = r["verdict"]
    summ["verdict_changed_between_variants"] = sum(1 for v in pairs.values() if len(v) == 2 and v["assertive"] != v["hedged"])
    summ["pairs"] = sum(1 for v in pairs.values() if len(v) == 2)
    (RES / "certainty_probe" / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
