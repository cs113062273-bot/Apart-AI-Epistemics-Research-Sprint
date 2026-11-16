"""Citation-support baselines with the local NLI cross-encoder (cross-encoder/nli-deberta-v3-small, ONNX, CPU).

nli_claim : premise = source excerpt, hypothesis = the cited claim (the usual citation-support check;
            it cannot see the user, so its verdict is the same in cases A, B and C).
nli_answer: premise = source excerpt + the user's situation, hypothesis = the whole recommendation.
Entailment -> 'correct' (no intervention); contradiction or neutral -> 'incorrect' (flag).
Premises longer than the 512-token window are narrowed to the lines around the quote (recorded).
    python scripts/run_nli.py --split test   ->  results/contrast/test_nli_claim.jsonl, test_nli_answer.jsonl
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models/nli-deberta-v3-small"  # Hugging Face cross-encoder/nli-deberta-v3-small (ONNX export)
LABELS = ["contradicted", "supported", "unknown"]  # the model's label order: contradiction, entailment, neutral
ITEMS = [json.loads(l) for l in open(ROOT / "data/contrast/items.jsonl", encoding="utf-8")]
OUT = ROOT / "results/contrast"

tok = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
tok.no_truncation()
sess = ort.InferenceSession(str(MODEL / "onnx/model_quint8_avx2.onnx"), providers=["CPUExecutionProvider"])
names = [i.name for i in sess.get_inputs()]


def narrow(excerpt, quote):
    lines = re.split(r"(?<=[.\n])\s+", excerpt)
    i = next((k for k, l in enumerate(lines) if quote[:40] in l), 0)
    return " ".join(lines[max(0, i - 1):i + 2])


def nli(premise, hypothesis, quote):
    narrowed = False
    enc = tok.encode(premise, hypothesis)
    if len(enc.ids) > 512:
        premise, narrowed = narrow(premise, quote), True
        enc = tok.encode(premise, hypothesis)
    ids = np.array([enc.ids[:512]], dtype=np.int64)
    feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.array([enc.type_ids[:512]], dtype=np.int64)
    logits = sess.run(None, {k: v for k, v in feed.items() if k in names})[0][0]
    return LABELS[int(np.argmax(logits))], narrowed


ap = argparse.ArgumentParser()
ap.add_argument("--split", default="test")
split = ap.parse_args().split
for arm in ("nli_claim", "nli_answer"):
    path = OUT / f"{split}_{arm}.jsonl"
    path.unlink(missing_ok=True)
    for item in (i for i in ITEMS if i["split"] == split):
        claim = re.sub(r" \(“.*?”\)", "", item["claim"])
        for case in item["cases"]:
            if arm == "nli_claim":
                label, narrowed = nli(item["excerpt"], claim, item["quote"])
            else:
                label, narrowed = nli(f"{item['excerpt']}\nUser: {case['context']}", case["answer"], item["quote"])
            row = {"item": item["id"], "label": case["label"], "domain": item["domain"], "family": item["family"],
                   "verdict": "correct" if label == "supported" else "incorrect", "corrected": label, "narrowed_premise": narrowed,
                   "gold": case["gold"], "n_calls": 0, "seconds": 0}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(arm, "done")
