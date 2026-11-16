"""Lynx-8B, a published faithfulness checker, on the contrast set, used as designed for RAG QA:
question = the user's situation + decision question, context = source excerpt, answer = the assistant's answer.
PASS is scored as 'correct' (no intervention), FAIL as 'incorrect'. Expects a Lynx server at config/lynx.json's endpoint.
    python scripts/run_lynx.py --split test   ->  results/contrast/test_lynx.jsonl
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from applicability import _question  # noqa: E402

CFG = json.loads((ROOT / "config/lynx.json").read_text(encoding="utf-8"))
ITEMS = [json.loads(l) for l in open(ROOT / "data/contrast/items.jsonl", encoding="utf-8")]
OUT = ROOT / "results/contrast"


def chat(body):
    req = urllib.request.Request(CFG["endpoint"].rstrip("/") + "/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


ap = argparse.ArgumentParser()
ap.add_argument("--split", default="test")
split = ap.parse_args().split
path = OUT / f"{split}_lynx.jsonl"
done = {(r["item"], r["label"]) for r in map(json.loads, open(path, encoding="utf-8"))} if path.exists() else set()
template = CFG["published_prompt"]["template"]
for item in (i for i in ITEMS if i["split"] == split):
    for case in item["cases"]:
        if (item["id"], case["label"]) in done:
            continue
        question = f"{case['context']} {_question(item, case)}"
        body = {"model": CFG["alias"], "temperature": 0, "seed": 20261115, "max_tokens": 600,
                "messages": [{"role": "user", "content": template.format(question=question, context=item["excerpt"], answer=case["answer"])}]}
        started = time.perf_counter()
        try:
            content = chat(body)["choices"][0]["message"]["content"]
            scores = re.findall(r'"?SCORE"?\s*:\s*"?\s*(PASS|FAIL)\b', content, re.I)
            verdict = ("correct" if scores[0].upper() == "PASS" else "incorrect") if len(scores) == 1 else "error"
        except Exception as exc:
            content, verdict = repr(exc), "error"
        row = {"item": item["id"], "label": case["label"], "domain": item["domain"], "family": item["family"], "verdict": verdict,
               "corrected": content[-600:], "gold": case["gold"], "n_calls": 1, "seconds": round(time.perf_counter() - started, 2)}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("lynx", item["id"], case["label"], verdict, flush=True)
