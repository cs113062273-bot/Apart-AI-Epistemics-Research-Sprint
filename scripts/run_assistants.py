"""Assistants write cited answers on a frozen natural-answer set; each answer is typed and turned into a verifier case.
    python scripts/run_assistants.py --set replication --model qwen3-4b    (CPU models: llama.cpp server on port 8085, started here)
    python scripts/run_assistants.py --set replication --model qwen35-9b   (uses the verifier server, config/verifier.json)
Writes data/<set>/answers/<model>.jsonl (raw calls) and data/<set>/answered/<model>.jsonl (cases with the assistant's answer,
gold and error type), which run_verifiers.py verifies with --set <set> --assistant <model>.

Error typing (automatic, from printed values): a wrong decision whose explanation or quote contains the case's trap value
(the printed value whose condition does not hold for this user) and not the applicable value is 'supported_inapplicable'
when the quoted trap text occurs in the source; 'applicable_value_misused' when the applicable value appears; else 'other'.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from applicability import answer_text, assist  # noqa: E402

DATA = ROOT / "data"
LLAMA_SERVER = os.environ.get("LLAMA_SERVER", "llama-server")
MODELS = {"qwen3-4b": "models/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf",  # bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF
          "qwen2.5-1.5b": "models/qwen2.5-1.5b-instruct-q4_k_m.gguf",  # Qwen/Qwen2.5-1.5B-Instruct-GGUF
          "smollm2-1.7b": "models/smollm2-1.7b-instruct-q4_k_m.gguf"}  # HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF
PORT = 8085


def healthy(port):
    try:
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read()).get("status") == "ok"
    except Exception:
        return False


def numbers(s):
    """Absolute values of every number written in s."""
    return {abs(float(n.replace(",", ""))) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


KEY_OVERRIDE = {"Outdoor 597,301 497,598 20% 1,497,571 1,426,451 5%": 5.0,  # the year-to-date change in the table row
                "0% (0/54) with CAG vs 21.1% (15/71) with AMT in patients aged 20-40 years": 21.1}


def key_number(t):
    """The distinguishing number of a printed snippet: its first number, unless overridden above."""
    if t in KEY_OVERRIDE:
        return KEY_OVERRIDE[t]
    return abs(float(re.findall(r"\d[\d,]*(?:\.\d+)?", t)[0].replace(",", "")))


def mentions(have, x):
    return any(abs(h - x) < 1e-6 for h in have)


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def type_error(item, case, out, correct):
    said = out["explanation"] + " " + out["quote"]
    have = numbers(said)
    trap, app = key_number(case["trap_text"]), key_number(case["applicable_text"])
    used_trap, used_app = mentions(have, trap), mentions(have, app)
    quote_in_source = bool(out["quote"].strip()) and norm(out["quote"])[:60] in norm(item["excerpt"])
    if correct:
        kind = "correct_with_trap_value" if used_trap and not used_app else "correct"
    elif used_trap and not used_app:
        kind = "supported_inapplicable"  # the trap value is printed in the source by construction (builder asserts it)
    elif used_app:
        kind = "applicable_value_misused"
    else:
        kind = "other"
    return kind, {"used_trap": used_trap, "used_applicable": used_app, "quote_in_source": quote_in_source}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", required=True, choices=["discovery", "replication"])
    a = ap.parse_args()
    items = [json.loads(l) for l in open(DATA / a.set / "items.jsonl", encoding="utf-8")]
    (DATA / a.set / "answers").mkdir(exist_ok=True)
    (DATA / a.set / "answered").mkdir(exist_ok=True)
    proc = None
    if a.model == "qwen35-9b":
        cfg = json.load(open(ROOT / "config/verifier.json", encoding="utf-8"))
        endpoint, alias = cfg["endpoint"], cfg["alias"]
    else:
        assert not healthy(PORT), "port 8085 already in use; not starting a second server"
        log = open(ROOT / f"server_{a.model}.log", "a", encoding="utf-8")
        proc = subprocess.Popen([LLAMA_SERVER, "-m", str(ROOT / MODELS[a.model]), "--host", "127.0.0.1", "--port", str(PORT),
                                 "--alias", a.model, "--jinja", "-ngl", "0", "-c", "8192", "-np", "1", "-t", "10"],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        t0 = time.time()
        while not healthy(PORT):
            assert proc.poll() is None and time.time() - t0 < 300, "assistant server failed to start"
            time.sleep(1)
        endpoint, alias = f"http://127.0.0.1:{PORT}/v1", a.model
    raw_path = DATA / a.set / "answers" / f"{a.model}.jsonl"
    done = {(r["item"], r["label"]): r for r in map(json.loads, open(raw_path, encoding="utf-8"))} if raw_path.exists() else {}
    try:
        for item in items:
            for case in item["cases"]:
                if (item["id"], case["label"]) in done:
                    continue
                try:
                    out, rec = assist(item, case, endpoint, alias)
                except Exception as exc:
                    out, rec = None, {"error": repr(exc)[:300], "seconds": 0}
                row = {"item": item["id"], "label": case["label"], "out": out, "seconds": rec.get("seconds"), "record": rec}
                with open(raw_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                done[(item["id"], case["label"])] = row
                print(a.model, item["id"], case["label"], (out or {}).get("decision"), case["truth"], row["seconds"], flush=True)
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=30)
    # build the verifier cases
    built, tally = [], {}
    for item in items:
        cases = []
        for case in item["cases"]:
            out = done[(item["id"], case["label"])]["out"]
            if not out:
                kind, info, correct = "no_answer", {}, False
            else:
                correct = out["decision"] == case["truth"]
                kind, info = type_error(item, case, out, correct)
            tally[kind] = tally.get(kind, 0) + 1
            if not out:
                continue  # no answer to verify; counted in the tally
            cases.append({"label": case["label"], "context": case["context"], "answer": answer_text(item, out), "quote": out["quote"],
                          "assistant_decision": out["decision"], "error_type": kind, "typing": info,
                          "gold": {"answer_correct": correct, "applies": "yes" if case["label"] == "A" else "no", "correct_recommendation": case["truth"]}})
        built.append({**{k: v for k, v in item.items() if k != "cases"}, "quote": "", "assistant": a.model, "cases": cases})
    with open(DATA / a.set / "answered" / f"{a.model}.jsonl", "w", encoding="utf-8") as f:
        for it in built:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print("error types", tally)


if __name__ == "__main__":
    main()
