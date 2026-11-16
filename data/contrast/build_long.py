"""Long-document stress condition (added after dev results showed a ceiling for LLM judges on short
excerpts; built and committed before any test-split run). Same items, cases, answers and gold labels as
items.jsonl; only the excerpt is widened to the surrounding page or release text (~12k characters), so
the printed condition competes with every other plan, period and figure on the page. Science abstracts
are already complete and are left out of this condition.
"""
import json
import re
from pathlib import Path

import importlib.util
_spec = importlib.util.spec_from_file_location("contrast_build", Path(__file__).resolve().parents[1] / "contrast" / "build.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)  # rebuilds the contrast items in memory with the same specs

HERE = Path(__file__).parent
SRC = HERE.parent / "sources"
CAP = 12000
TAG = {"Asana pricing": "as", "Basecamp pricing": "bc", "Notion pricing": "no", "Proton Mail pricing": "pm", "Proton VPN pricing": "pv",
       "GitHub pricing": "gh", "Loom pricing": "lo", "Tailscale pricing": "tl", "Hetzner Storage Box": "hz"}


def widen_page(tag, excerpt):
    segs = [s["text"].strip() for s in json.load(open(SRC / "pricing" / f"{tag}.json", encoding="utf-8"))["segments"]]
    idx = [segs.index(ln.strip()) for ln in excerpt.split("\n") if ln.strip() in segs]
    lo, hi = min(idx), max(idx)  # start from the original excerpt, then grow
    while True:
        grown = False
        for lo2, hi2 in ((lo - 1, hi), (lo, hi + 1)):
            if 0 <= lo2 and hi2 < len(segs) and len("\n".join(s for s in segs[lo2:hi2 + 1] if s)) <= CAP:
                lo, hi, grown = lo2, hi2, True
        if not grown:
            break
    return "\n".join(s for s in segs[lo:hi + 1] if s)


def widen_release(name, excerpt):
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z•])", B.release_text(name))
    idx = [i for i, s in enumerate(sents) if s.strip() and s.strip() in excerpt]
    lo, hi = min(idx), max(idx)
    while True:
        grown = False
        for lo2, hi2 in ((lo - 1, hi), (lo, hi + 1)):
            if 0 <= lo2 and hi2 < len(sents) and len(" ".join(sents[lo2:hi2 + 1])) <= CAP:
                lo, hi, grown = lo2, hi2, True
        if not grown:
            break
    return " ".join(sents[lo:hi + 1])


rows = [json.loads(l) for l in open(HERE / "items.jsonl", encoding="utf-8")]
out = []
for item in rows:
    if item["domain"] == "science":
        continue
    if item["domain"] == "procurement":
        wide = widen_page(TAG[item["source"][0]], item["excerpt"])
    else:
        wide = widen_release(item["source"][1], item["excerpt"])
    for needed in [item["quote"], item.get("alt_text")] + [ln for ln in item["excerpt"].split("\n") if ln.strip()]:
        if needed:
            assert needed.strip() in wide or needed[:60] in wide, (item["id"], needed[:80])
    out.append(dict(item, excerpt=wide, condition="long"))
with open(HERE / "items_long.jsonl", "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(out), "items;", sum(r["split"] == "test" for r in out), "test;", "mean chars", sum(len(r["excerpt"]) for r in out) // len(out))
