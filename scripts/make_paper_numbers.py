"""Write paper/numbers.tex (every number and generated table in the paper) from the scored results. No model calls.
    python scripts/make_paper_numbers.py
Macro prefixes: T = contrast test split, V = held-out set, L = long-excerpt set, N = discovery set, W = replication set.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import run_verifiers as R  # noqa: E402

DATA, RES = ROOT / "data", ROOT / "results"
HELDOUT = R.SETS["heldout"][2]  # split label stored in the frozen held-out items

NAMES = [("nli_claim", "NLI: excerpt $\\to$ claim"), ("nli_answer", "NLI: excerpt+situation $\\to$ answer"),
         ("lynx", "Lynx-8B faithfulness"), ("rules", "Qualifier rules"), ("judge", "LLM judge (sees situation)"),
         ("judge_checklist", "Checklist LLM judge"), ("direct", "Direct answer from excerpt (ignores answer)"), ("dcv", "DCV (slot reading + code)"), ("qbr-judge_only", "QBR without code (judge verdict)"),("qbr", "\\textbf{QBR (quote-bound recalculation)}")]
FAMILY = {"billing_period": "Billing term", "intro_vs_renewal": "Intro vs renewal", "per_user": "Per-user price", "tax_basis": "Tax basis",
          "gaap_basis": "Accounting basis", "reporting_period": "Reporting period", "relative_vs_absolute": "Relative vs absolute",
          "population_scope": "Study population", "quota_overage": "Included quota + overage", "minimum_charge": "Minimum billable amount",
          "units_gib_gb": "GiB vs GB", "user_cap": "Plan user cap", "segment_vs_consolidated": "Segment vs consolidated",
          "currency_basis": "Constant currency vs reported", "guidance_vs_reported": "Guidance vs reported"}


def fp(p):
    """'=0.48' or '<0.001' (the summary rounds p to 4 decimals)."""
    return "<0.001" if p < 0.001 else f"={p:.2g}"


def tag(s):
    return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))


def summary(split, set_name):
    R.use_set(set_name)
    try:
        return R.score(split, quiet=True), list(R.ITEMS)
    except Exception as exc:  # a study that has not run yet
        print("skip", split, set_name, exc)
        return None, list(R.ITEMS)


def rows(summ, items, split):
    nb = sum(1 for i in items if i["split"] == split for c in i["cases"] if c["label"] == "B")
    nc = sum(1 for i in items if i["split"] == split for c in i["cases"] if c["label"] == "C")
    na = sum(1 for i in items if i["split"] == split for c in i["cases"] if c["label"] == "A")
    out = [f"No verifier (answer as given) & {summ['no_verifier_decision_accuracy']} & --- & 0/{nb} & {nc}/{nc} & 0 & 0 & --- \\\\"]
    for key, label in NAMES:
        a = summ["arms"].get(key)
        if not a:
            continue
        ci = a["decision_accuracy_item_bootstrap_ci95"]
        p = a.get("vs_judge_checklist_paired", {})
        pp = "---" if key == "judge_checklist" else f"{p.get('this_only_right', 0)}/{p.get('judge_checklist_only_right', 0)}, $p{fp(p.get('exact_mcnemar_p', 1))}$"
        out.append(f"{label} & {a['decision_accuracy']} & [{ci[0]:.2f}, {ci[1]:.2f}] & {a['B_wrong_answer_caught_and_fixed']} & "
                   f"{a['C_kept_irrelevant_mismatch']} & {a['wrong_interventions_on_right_answers']} & {a['calls']} & {pp} \\\\")
    return "\n".join(out)


def main():
    mac = {}  # a later definition of the same name overrides an earlier one
    m = lambda k, v: mac.__setitem__(k, v)  # noqa: E731
    s1, contrast_items = summary("test", "contrast")
    s2, heldout_items = summary(HELDOUT, "heldout")
    sl, _ = summary("test", "contrast_long")
    R.use_set("contrast")
    m("NItems", len(contrast_items)); m("NCases", sum(len(i["cases"]) for i in contrast_items))
    dom = Counter(i["domain"] for i in contrast_items)
    m("NProc", dom["procurement"]); m("NFin", dom["finance"]); m("NSci", dom["science"])
    test = [i for i in contrast_items if i["split"] == "test"]
    m("NTestItems", len(test)); m("NTestCases", sum(len(i["cases"]) for i in test))
    m("NVItems", len(heldout_items)); m("NVCases", sum(len(i["cases"]) for i in heldout_items))
    m("NCasesAll", sum(len(i["cases"]) for i in contrast_items) + sum(len(i["cases"]) for i in heldout_items))
    m("NVNewType", sum(i["family"] not in {x["family"] for x in contrast_items} for i in heldout_items))
    fam1 = Counter(i["family"] for i in contrast_items)
    fam2 = Counter(i["family"] for i in heldout_items)
    m("FamilyRows", "\n".join(f"{FAMILY[f]} & {fam1.get(f, 0)} & {fam2.get(f, 0)} \\\\" for f in FAMILY if fam1.get(f) or fam2.get(f)))
    for prefix, summ, items, split in (("T", s1, contrast_items, "test"), ("V", s2, heldout_items, HELDOUT), ("L", sl, None, "test")):
        if not summ:
            m(f"{prefix}Rows", "\\multicolumn{8}{c}{(not yet run)} \\\\")
            continue
        if items is not None:
            m(f"{prefix}Rows", rows(summ, items, split))
        m(f"{prefix}None", summ["no_verifier_decision_accuracy"])
        for key, a in summ["arms"].items():
            t = tag(key)
            m(f"{prefix}Acc{t}", a["decision_accuracy"])
            m(f"{prefix}Fix{t}", a["B_wrong_answer_caught_and_fixed"]); m(f"{prefix}Keep{t}", a["C_kept_irrelevant_mismatch"])
            m(f"{prefix}Alarm{t}", a["A_false_alarm"]); m(f"{prefix}Wrong{t}", a["wrong_interventions_on_right_answers"])
            ci = a["decision_accuracy_item_bootstrap_ci95"]
            m(f"{prefix}Ci{t}", f"[{ci[0]:.2f}, {ci[1]:.2f}]")
            p = a.get("vs_judge_checklist_paired")
            if p:
                m(f"{prefix}P{t}", fp(p['exact_mcnemar_p']))
                m(f"{prefix}Only{t}", p["this_only_right"]); m(f"{prefix}OnlyCk{t}", p["judge_checklist_only_right"])
            if key.startswith("qbr") and a.get("decided_by"):
                d = a["decided_by"]
                code = d.get("code", "0/0 right").split()[0]
                m(f"{prefix}Code{t}", code)
                m(f"{prefix}Strata{t}", "; ".join(f"{k}: {v.replace(' right', '')}" for k, v in sorted(d.items())))
        abl = []
        for key, label in (("dcv", "DCV, full"), ("dcv-no_counterfactual", "$-$ recompute-and-flip (flag any mismatch)"), ("dcv-no_selection", "$-$ variant selection"),
                           ("dcv-no_arithmetic", "$-$ user arithmetic"), ("dcv-no_abstention", "$-$ abstention"),
                           ("qbr", "QBR, code verdict when certified (pre-registered)"), ("qbr-agree", "QBR, intervene only if code and judge agree"),
                           ("qbr-judge_only", "QBR without code (judge verdict)")):
            a = summ["arms"].get(key)
            if a:
                abl.append(f"{label} & {a['decision_accuracy']} & {a['B_wrong_answer_caught_and_fixed']} & {a['C_kept_irrelevant_mismatch']} & {a['wrong_interventions_on_right_answers']} \\\\")
        m(f"{prefix}AblRows", "\n".join(abl))
        for key, a in summ["arms"].items():
            m(f"{prefix}AllRight{tag(key)}", a["items_all_cases_right"])
        ia_path = RES / {"T": "contrast/test_item_analysis.json", "V": "heldout/item_analysis.json", "L": "contrast_long/test_item_analysis.json"}[prefix]
        if ia_path.exists():  # paired, item-bootstrap differences (scripts/item_analysis.py)
            ia = json.loads(ia_path.read_text(encoding="utf-8"))
            for p in ia["paired"]:
                t = tag(p["x"]) + "Vs" + tag(p["y"])
                lo, hi = p["diff_item_bootstrap_ci95"]
                m(f"{prefix}Pair{t}", f"{p['x_only_right']}/{p['y_only_right']}")
                m(f"{prefix}PairP{t}", fp(p['exact_mcnemar_p']))
                m(f"{prefix}DiffCi{t}", f"[{lo:.2f}, {hi:.2f}]".replace("-0.00", "0.00"))
            if prefix == "V":
                show = ["judge_checklist", "qbr-judge_only", "qbr", "dcv", "rules"]
                lines = []
                for iid, row in ia["per_item_cases_right"].items():
                    cells = " & ".join("\\texttt{" + row[a] + "}" for a in show)
                    lines.append(f"{iid.split('-', 1)[1]} & {FAMILY[row['family']]} & \\texttt{{{ia['no_verifier_per_item'][iid]}}} & {cells} \\\\")
                m("VItemRows", "\n".join(lines))
    both = [("nli_claim", "NLI: excerpt $\\to$ claim"), ("nli_answer", "NLI: excerpt + situation $\\to$ answer"), ("lynx", "Lynx-8B faithfulness"),
            ("rules", "Qualifier rules"), ("judge", "LLM judge (sees situation)"), ("judge_checklist", "\\textbf{Checklist LLM judge}"),
            ("direct", "Direct answer (ignores the answer)"), ("dcv", "DCV (slot reading + code)"),
            ("qbr-judge_only", "QBR without code (judge verdict)"), ("qbr", "QBR (quote-bound recalculation)")]

    def cols(summ, key, items, split):
        if summ is None or key not in summ["arms"]:
            return "\\multicolumn{4}{c}{---}"
        a = summ["arms"][key]
        lo, hi = a["decision_accuracy_item_bootstrap_ci95"]
        return f"{a['decision_accuracy']} & [{lo:.2f}, {hi:.2f}] & {a['B_wrong_answer_caught_and_fixed'].split('/')[0]} & {a['C_kept_irrelevant_mismatch'].split('/')[0]}"
    nb = lambda items, split, lab: sum(1 for i in items if i["split"] == split for c in i["cases"] if c["label"] == lab)
    lines = [f"No verifier & {s1['no_verifier_decision_accuracy']} & --- & 0 & {nb(contrast_items, 'test', 'C')} & "
             f"{s2['no_verifier_decision_accuracy']} & --- & 0 & {nb(heldout_items, HELDOUT, 'C')} \\\\ \\midrule"]
    for key, label in both:
        if key not in s1["arms"] and key not in s2["arms"]:
            continue
        lines.append(f"{label} & {cols(s1, key, contrast_items, 'test')} & {cols(s2, key, heldout_items, HELDOUT)} \\\\")
    m("BothRows", "\n".join(lines))
    m("TNB", nb(contrast_items, "test", "B")); m("TNC", nb(contrast_items, "test", "C")); m("VNB", nb(heldout_items, HELDOUT, "B")); m("VNC", nb(heldout_items, HELDOUT, "C"))
    la = (sl or {}).get("arms", {})
    m("LongSentence", (f"With the same test items' excerpts widened to about 12k characters (the same items, so not additional independent evidence), "
                       f"the checklist judge reached {la['judge_checklist']['decision_accuracy']} and QBR {la['qbr']['decision_accuracy']}, "
                       f"against {sl['no_verifier_decision_accuracy']} for leaving answers alone.")
      if la.get("judge_checklist") and la.get("qbr") and la["qbr"]["cases"] == la["judge_checklist"]["cases"] else "")
    fams = [f for f in FAMILY if fam1.get(f) or fam2.get(f)]
    half = (len(fams) + 1) // 2
    cells = [f"{FAMILY[f]} & {fam1.get(f, 0)} & {fam2.get(f, 0)}" for f in fams] + [" & & "]
    m("FamilyRowsTwoCol", "\n".join(f"{cells[i]} & {cells[i + half]} \\\\" for i in range(half)))
    ly = (s1 or {}).get("arms", {}).get("lynx")
    m("LynxSentence", (f"Lynx-8B, a published faithfulness checker run with its own prompt, reaches {ly['decision_accuracy']} "
                       f"(B fixed {ly['B_wrong_answer_caught_and_fixed']}, false alarms on A {ly['A_false_alarm']}, C kept {ly['C_kept_irrelevant_mismatch']}).")
      if ly else "")
    # natural-answer studies: discovery (prefix N) and the pre-registered replication (prefix W)
    tagm = {"qwen35-9b": "Nine", "qwen3-4b": "Four", "qwen2.5-1.5b": "OneFive", "smollm2-1.7b": "Smol"}
    for sname, P in (("discovery", "N"), ("replication", "W")):
        sp = RES / sname / "analysis.json"
        if not sp.exists():
            continue
        sv = json.loads(sp.read_text(encoding="utf-8"))
        for mdl, t in tagm.items():
            d = sv.get(mdl) or {}
            if d.get("audit"):
                a = d["audit"]
                m(f"{P}{t}Wrong", a["wrong_total"]); m(f"{P}{t}SI", a["totals"].get("supported_inapplicable", 0))
                m(f"{P}{t}Amb", a["totals"].get("ambiguous_value", 0)); m(f"{P}{t}BWrong", a["B_wrong"]); m(f"{P}{t}BSI", a["B_supported_inapplicable"])
                m(f"{P}{t}NoAns", a["totals"].get("no_answer", 0))
                m(f"{P}{t}RightWrongReason", a["totals"].get("right_with_inapplicable_value", 0) + a["totals"].get("right_for_wrong_reason", 0))
            if d.get("prevalence"):
                m(f"{P}{t}AutoSI", sum(d["prevalence"][lab]["supported_inapplicable"] for lab in "ABC"))
            v = d.get("verifiers") or {}
            for arm, at in (("no_verifier", "None"), ("rules", "Rules"), ("judge", "Judge"), ("judge_checklist", "Ck"),
                            ("qbr-judge_only", "QbrJ"), ("qbr", "QbrBF"), ("qbr-source_bound", "Qbr")):
                x = v.get(arm)
                if not x or "decision_accuracy" not in x:
                    continue
                m(f"{P}{t}Acc{at}", x["decision_accuracy"]); m(f"{P}{t}Ci{at}", f"[{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}]")
                if "wrong_fixed" in x:
                    m(f"{P}{t}Fix{at}", x["wrong_fixed"]); m(f"{P}{t}Keep{at}", x["right_kept"]); m(f"{P}{t}SIFix{at}", x.get("si_fixed", ""))
                if "certified" in x:
                    m(f"{P}{t}Cert{at}", x["certified"])
            if "certified" in (v.get("qbr") or {}) and "certified" in (v.get("qbr-source_bound") or {}):
                n_bf, n_sb = (int(v[a]["certified"].split("/")[1]) for a in ("qbr", "qbr-source_bound"))
                m(f"{P}{t}CertNoSource", n_bf - n_sb); m(f"{P}{t}CertBoundFirst", n_bf)
            if "errors" in (v.get("qbr-source_bound") or {}):
                m(f"{P}{t}QbrErrors", v["qbr-source_bound"]["errors"])
            for pr in v.get("paired", []):
                m(f"{P}{t}Pair{tag(pr['x'])}Vs{tag(pr['y'])}", f"{pr['x_only']}/{pr['y_only']}"); m(f"{P}{t}PairP{tag(pr['x'])}Vs{tag(pr['y'])}", fp(pr["p"]))
        if sv.get("H1"):
            m(f"{P}HStrong", sv["H1"]["strong_si_of_wrong"]); m(f"{P}HWeak", sv["H1"]["weak_si_of_wrong"]); m(f"{P}HP", fp(sv["H1"]["fisher_one_sided_p"]))
        bs = [json.loads(l) for l in open(DATA / sname / "items.jsonl", encoding="utf-8")]
        m(f"{P}NItems", len(bs)); m(f"{P}NCases", sum(len(i["cases"]) for i in bs))
        m(f"{P}NFin", sum(i["domain"] == "finance" for i in bs)); m(f"{P}NSci", sum(i["domain"] == "science" for i in bs))
    # source-clustered statistics (scripts/natural_statistics.py): H1 both ways, verifier paired differences, certificate intervals
    pct = lambda x: f"{100 * x:.0f}\\%"  # noqa: E731
    ci = lambda c, f=pct: f"[{f(c[0])}, {f(c[1])}]"  # noqa: E731
    pp = lambda x: f"{100 * x:+.0f}".replace("+0", "0").replace("-0", "0").replace("+", "$+$").replace("-", "$-$")  # noqa: E731
    pci = lambda c: f"[{pp(c[0])}, {pp(c[1])}]"  # noqa: E731
    for sname, P in (("discovery", "N"), ("replication", "W")):
        rp = RES / sname / "statistics.json"
        if not rp.exists():
            continue
        rg = json.loads(rp.read_text(encoding="utf-8"))
        for mdl, t in tagm.items():
            r = rg["rates"].get(mdl)
            if r:
                m(f"{P}{t}WrongRate", pct(r["wrong"] / r["cases"])); m(f"{P}{t}WrongRateCi", ci(r["wrong_rate_source_ci95"]))
                m(f"{P}{t}SIRate", pct(r["si"] / r["cases"])); m(f"{P}{t}SIRateCi", ci(r["si_rate_source_ci95"]))
        for key, Q in (("H1", "H"), ("H1_excluding_contested_and_template_items", "HX")):
            h = rg.get(key)
            if not h:
                continue
            sh, pa = h["si_share_of_wrong"], h["si_per_answer"]
            m(f"{P}{Q}Strong", sh["strong"]); m(f"{P}{Q}Weak", sh["weak"])
            m(f"{P}{Q}ShareDiff", pp(sh["difference"])); m(f"{P}{Q}ShareDiffCi", pci(sh["difference_source_cluster_ci95"]))
            m(f"{P}{Q}P", fp(sh["fisher_one_sided_p_treating_errors_as_independent"]))
            m(f"{P}{Q}RateStrong", pa["strong"]); m(f"{P}{Q}RateWeak", pa["weak"])
            m(f"{P}{Q}RateDiff", pp(pa["difference"])); m(f"{P}{Q}RateDiffCi", pci(pa["difference_source_cluster_ci95"]))
            lo = h["leave_one_source_out_share_difference"]
            m(f"{P}{Q}LosoMin", pp(lo["min"])); m(f"{P}{Q}LosoMax", pp(lo["max"])); m(f"{P}{Q}LosoP", fp(lo["max_fisher_p"]))
            m(f"{P}{Q}Sources", h["n_sources"])
            m(f"{P}{Q}WrongStrong", h["strong"]["wrong"]); m(f"{P}{Q}WrongWeak", h["weak"]["wrong"])
            m(f"{P}{Q}SIStrong", h["strong"]["si"]); m(f"{P}{Q}SIWeak", h["weak"]["si"]); m(f"{P}{Q}Answers", h["strong"]["answers"])
        for mdl, t in tagm.items():
            vv = (rg.get("verifiers") or {}).get(mdl) or {}
            for arm, at in (("no_verifier", "None"), ("rules", "Rules"), ("judge", "Judge"), ("judge_checklist", "Ck"),
                            ("qbr-judge_only", "QbrJ"), ("qbr-source_bound", "Qbr")):
                x = vv.get(arm) or {}
                if "answered_accuracy" not in x:
                    continue
                m(f"{P}{t}Ans{at}", x["answered_accuracy"]); m(f"{P}{t}End{at}", x["end_to_end_accuracy"])
                if "fixed" in x:
                    m(f"{P}{t}Fixed{at}", x["fixed"]); m(f"{P}{t}Broken{at}", x["broken"])
                    m(f"{P}{t}Diff{at}", pp(x["accuracy_difference_vs_none"])); m(f"{P}{t}DiffCi{at}", pci(x["difference_source_cluster_ci95"]))
                c = x.get("certificate")
                if c:
                    m(f"{P}{t}CertCov", c["coverage"]); m(f"{P}{t}CertPrec", c["precision"])
                    m(f"{P}{t}CertCi", ci(c["precision_exact_ci95"], lambda v: f"{v:.3f}".rstrip("0").rstrip(".")))
                    m(f"{P}{t}CertVsJ", f"{c['vs_judge_only_fixed']}/{c['vs_judge_only_broken']}")
    # every audited supported-but-inapplicable error of the two strongest assistants (appendix table)
    short = {"qwen3-4b": "4B", "qwen35-9b": "9B"}
    groups = {}
    for s in ("discovery", "replication"):
        for mdl in ("qwen3-4b", "qwen35-9b"):
            p = RES / s / "audit" / f"{mdl}.json"
            if not p.exists():
                continue
            for r in json.loads(p.read_text(encoding="utf-8")):
                if r["category"] == "supported_inapplicable":
                    reason = re.sub(r"\s*Automatic typing[^.]*(\.[^ ][^.]*)*\.", "", r["reason"]).strip()  # internal note, not part of the case
                    groups[(s, r["item"], r["label"], short[mdl])] = {"models": [short[mdl]], "reason": reason}  # one row per assistant: reasons differ
    tex = lambda t: t.replace("\\", "/").replace("%", "\\%").replace("$", "\\$").replace("&", "\\&").replace("#", "\\#").replace("_", "\\_").replace("~", "\\textasciitilde{}")  # noqa: E731
    lines = ["\\begin{tabular}{@{}l l l p{11.2cm}@{}}", "\\toprule", "Set & Item, case & By & Audit reason \\\\", "\\midrule"]
    for (s, item, lab, _), g in sorted(groups.items()):
        lines.append(f"{s.capitalize()} & {tex(item.split('-', 1)[1])} {lab} & {', '.join(g['models'])} & {tex(g['reason'])} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    m("SIRows", "\n".join(lines))
    # certificates pooled over the two verified assistants (replication: pre-registered H3), exact binomial interval
    for sname, P in (("discovery", "N"), ("replication", "W")):
      rp = RES / sname / "statistics.json"
      an4 = RES / sname / "analysis.json"
      if rp.exists() and an4.exists():
          rg, av = json.loads(rp.read_text(encoding="utf-8")), json.loads(an4.read_text(encoding="utf-8"))
          certs = [(rg["verifiers"].get(mdl) or {}).get("qbr-source_bound", {}).get("certificate") for mdl in ("qwen3-4b", "qwen35-9b")]
          bfs = [((av.get(mdl) or {}).get("verifiers") or {}).get("qbr", {}).get("certified") for mdl in ("qwen3-4b", "qwen35-9b")]
          if all(certs) and all(bfs):
              from scipy.stats import beta
              k = sum(int(c["precision"].split("/")[0]) for c in certs); n = sum(int(c["precision"].split("/")[1]) for c in certs)
              cov = sum(int(c["coverage"].split("/")[0]) for c in certs); tot = sum(int(c["coverage"].split("/")[1]) for c in certs)
              lo = beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0
              hi = beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
              nbf = sum(int(b.split("/")[1]) for b in bfs)
              m(f"{P}CertPooled", f"{k}/{n}"); m(f"{P}CertPooledCi", f"[{lo:.2f}, {hi:.3f}]".replace("1.000", "1"))
              m(f"{P}CertPooledCov", f"{cov}/{tot}"); m(f"{P}CertBoundFirstPooled", nbf); m(f"{P}CertNoSourcePooled", nbf - n)
    # exploratory anchoring probe, masked re-audit, gold validity
    res = RES
    if (res / "certainty_probe/summary.json").exists():
        a = json.loads((res / "certainty_probe/summary.json").read_text(encoding="utf-8"))
        for k, t in (("wrong/assertive", "WrongAssert"), ("wrong/hedged", "WrongHedge"), ("right/assertive", "RightAssert"), ("right/hedged", "RightHedge")):
            m(f"Anc{t}", a[k].split(" ")[0])
        m("AncChanged", a["verdict_changed_between_variants"]); m("AncPairs", a["pairs"])
    if (res / "masked_reaudit/summary.json").exists():
        a = json.loads((res / "masked_reaudit/summary.json").read_text(encoding="utf-8"))
        m("MrRows", a["rows"]); m("MrAgree", a["exact_agreement"]); m("MrKappa", f"{a['kappa_all_categories']:.2f}")
        m("MrSI", a["si_vs_rest"]["both_si"]); m("MrSIOff", a["si_vs_rest"]["first_only"] + a["si_vs_rest"]["second_only"])
    if (res / "gold_check.json").exists():
        g = json.loads((res / "gold_check.json").read_text(encoding="utf-8"))
        m("GvCases", sum(g[s]["cases"] for s in g)); m("GvMismatch", sum(len(g[s]["recomputed_gold_mismatches"]) for s in g))
        m("GvContested", sum(len(g[s]["gold_contestable_cases"]) for s in g))
        m("GvTemplateItems", sum(len(g[s]["template_ambiguous_items"]) for s in g))
        m("GvTemplateCases", sum(g[s]["cases_in_template_ambiguous_items"] for s in g))
    # natural-answer verifier table: columns = (set, assistant) blocks; rows = verifiers
    blocks = [("discovery", "qwen3-4b", "Discovery, Qwen3-4B"), ("discovery", "qwen35-9b", "Discovery, Qwen3.5-9B (self)"),
              ("replication", "qwen3-4b", "Replication, Qwen3-4B"), ("replication", "qwen35-9b", "Replication, Qwen3.5-9B (self)")]
    an = {s: json.loads((RES / s / "analysis.json").read_text(encoding="utf-8"))
          for s in ("discovery", "replication") if (RES / s / "analysis.json").exists()}
    vrows = [("no_verifier", "No verifier"), ("rules", "Qualifier rules"), ("judge", "LLM judge"), ("judge_checklist", "Checklist judge"),
             ("qbr-source_bound", "QBR")]
    head = " & ".join(f"\\multicolumn{{3}}{{c}}{{{lab}}}" for _, _, lab in blocks)
    cm = "".join(f"\\cmidrule(lr){{{2 + 3 * i}-{4 + 3 * i}}}" for i in range(len(blocks)))
    lines = ["\\resizebox{\\textwidth}{!}{\\begin{tabular}{l" + "ccc" * len(blocks) + "}", "\\toprule", f" & {head} \\\\", cm,
             "Verifier" + " & Acc. & Inapp. fixed & Right kept" * len(blocks) + " \\\\", "\\midrule"]
    for key, lab in vrows:
        cells = []
        for s, mdl, _ in blocks:
            x = ((an.get(s) or {}).get(mdl) or {}).get("verifiers") or {}
            x = x.get(key) or {}
            if "decision_accuracy" not in x:
                cells += ["--", "--", "--"]
            elif key == "no_verifier":
                cells += [x["decision_accuracy"], "0", "all"]
            else:
                cells += [x["decision_accuracy"], x.get("si_fixed", "--"), x.get("right_kept", "--")]
        lines.append(f"{lab} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}}"]
    m("NatTable", "\n".join(lines))
    m("NCasesAllNat", sum(len(i["cases"]) for i in contrast_items) + sum(len(i["cases"]) for i in heldout_items) +
      sum(sum(len(i["cases"]) for i in map(json.loads, open(DATA / s / "items.jsonl", encoding="utf-8")))
          for s in ("discovery", "replication") if (DATA / s / "items.jsonl").exists()))
    qp = RES / "qbr_certificates.json"
    if qp.exists():  # post-hoc decomposition of QBR's certificate (scripts/qbr_certificates.py)
        q = json.loads(qp.read_text(encoding="utf-8"))
        for pre, k in (("T", "contrast_test"), ("V", "heldout")):
            d = q[k]
            m(f"{pre}QpCases", d["cases"]); m(f"{pre}QpStructured", d["structured_output"]); m(f"{pre}QpTraceable", d["all_used_traceable"])
            m(f"{pre}QpCertified", d["certified"]); m(f"{pre}QpUsesSource", d["certified_uses_source"])
            m(f"{pre}QpCertCorrect", d["certified_correct"]); m(f"{pre}QpSourceCorrect", d["certified_uses_source_correct"])
            m(f"{pre}QpNoSource", len(d["certified_without_source"]))
            m(f"{pre}QpRuleAcc", f"{d['source_rule_accuracy']}/{d['cases']}")
        sv = q["heldout_seen_vs_new_condition_type"]
        for arm in ("judge_checklist", "qbr", "no_verifier"):
            m(f"VSeen{tag(arm)}", sv[arm]["seen_type"]); m(f"VNew{tag(arm)}", sv[arm]["new_type"])
    macros = [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in mac.items()]
    (ROOT / "paper/numbers.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")
    print(f"wrote {len(macros)} macros")


if __name__ == "__main__":
    main()
