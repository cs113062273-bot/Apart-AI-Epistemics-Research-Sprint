"""Paper figures, drawn from the scored results only (no model calls).
    python scripts/make_figures.py
  paper/figures/natural_errors.pdf  wrong decisions in natural cited answers by audited cause (discovery, replication)
  paper/figures/verifiers.pdf       (a) wrong answers fixed vs harmless mismatches kept, contrast test split; (b) what QBR's certificate establishes
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
ARMS = [("lynx", "Lynx-8B (support check)"), ("nli_claim", "NLI (support check)"), ("rules", "Qualifier rules"), ("judge", "LLM judge"),
        ("judge_checklist", "Checklist judge"), ("dcv", "DCV (slots + code)"), ("qbr-judge_only", "QBR, judge verdict only"), ("qbr", "QBR")]

plt.rcParams.update({"font.family": "serif", "font.size": 8.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": INK, "pdf.fonttype": 42})


def frac(s):
    a, b = s.split("/")
    return int(a) / int(b)


def tidy(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_axisbelow(True)


def mechanisms():
    contrast = json.loads((RES / "contrast" / "test_summary.json").read_text(encoding="utf-8"))
    q = json.loads((RES / "qbr_certificates.json").read_text(encoding="utf-8"))
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 3.15), gridspec_kw={"width_ratios": [1, 1.15]})
    # (a) wrong answers fixed vs irrelevant mismatches kept
    pts = [("No verifier", 0.0, 1.0)]
    names = dict(ARMS + [("nli_answer", "NLI (answer)")])
    for k in ("lynx", "nli_claim", "nli_answer", "rules", "judge", "judge_checklist", "dcv", "qbr"):
        x = contrast["arms"].get(k)
        if x:
            pts.append((names[k].replace(" (support check)", "").replace(" (slots + code)", ""), frac(x["B_wrong_answer_caught_and_fixed"]), frac(x["C_kept_irrelevant_mismatch"])))
    a.add_patch(plt.Rectangle((.75, .75), .3, .3, color="#e9f2fb", zorder=0, lw=0))
    a.text(1.02, 1.02, "goal", ha="right", va="top", fontsize=7, color=MUTED)
    place = {"No verifier": (6, -9, "left"), "Qualifier rules": (-7, 0, "right"), "Checklist judge": (-7, 3, "right"),
             "QBR": (-7, -3, "right"), "LLM judge": (-6, -8, "right"), "DCV": (0, 9, "center"),
             "NLI": (-7, 0, "right"), "NLI (answer)": (0, -10, "center"), "Lynx-8B": (0, 8, "center")}
    for name, x, y in pts:
        a.plot(x, y, "o", ms=6, color=BLUE if name != "No verifier" else MUTED, mec=SURF, mew=1.2, zorder=3)
        dx, dy, ha = place.get(name, (6, 0, "left"))
        a.annotate(name, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=7, ha=ha, va="center", color=INK)
    a.set_xlim(-.05, 1.05)
    a.set_ylim(-.06, 1.06)
    a.set_xlabel("Wrong answers fixed (B)")
    a.set_ylabel("Harmless mismatches left alone (C)")
    a.set_title("(a) Fixing errors vs. leaving harmless mismatches", fontsize=8.5, loc="left")
    a.grid(color=GRID, lw=.6)
    tidy(a)
    # (b) what the certificate establishes
    rows = [("structured_output", "Structured output"), ("all_used_traceable", "Every operand traced\nto a printed quote"),
            ("certified", "Certified: condition\nchecks pass"), ("certified_uses_source", "...and uses a\nsource value"),
            ("certified_uses_source_correct", "...and decision right")]
    for j, (key, label, color) in enumerate((("contrast_test", "Contrast (test)", BLUE), ("heldout", "Held-out", ORANGE))):
        d = q[key]
        for i, (r, _) in enumerate(rows):
            y = len(rows) - i + (.18 if j == 0 else -.18)
            share = d[r] / d["cases"]
            b.barh(y, share, height=.34, color=color, label=label if i == 0 else None, zorder=2)
            b.text(share + .015, y, f"{d[r]}/{d['cases']}", va="center", fontsize=7, color=INK)
    b.set_yticks([len(rows) - i for i in range(len(rows))], [lab for _, lab in rows], fontsize=7.5)
    b.set_xlim(0, 1.18)
    b.set_xticks([0, .25, .5, .75, 1], ["0", "25%", "50%", "75%", "100%"])
    b.set_xlabel("Share of QBR cases")
    b.set_title("(b) What a QBR certificate shows", fontsize=8.5, loc="left")
    b.grid(axis="x", color=GRID, lw=.6)
    tidy(b)
    b.legend(loc="upper center", bbox_to_anchor=(.35, -.2), ncol=2, frameon=False, fontsize=7)
    fig.tight_layout(w_pad=1.2)
    save(fig, "verifiers")


def save(fig, name):
    out = ROOT / "paper" / "figures" / f"{name}.pdf"
    fig.savefig(out, metadata={"CreationDate": None})
    print("wrote", out)


def natural():
    """Headline: each assistant's wrong decisions on natural cited answers, split by audited cause, for the discovery set
    and the pre-registered replication. Supported-but-inapplicable errors are highlighted; everything else is grey."""
    sets = []
    for sname, title in (("discovery", "Discovery"), ("replication", "Pre-registered replication")):
        p_ = RES / sname / "analysis.json"
        if p_.exists():
            q = json.loads(p_.read_text(encoding="utf-8"))
            if any((q.get(m) or {}).get("audit") for m in ("qwen35-9b", "qwen3-4b", "qwen2.5-1.5b", "smollm2-1.7b")):
                sets.append((sname, title, q))
    if not sets:
        return
    names = [("smollm2-1.7b", "SmolLM2-1.7B"), ("qwen2.5-1.5b", "Qwen2.5-1.5B"), ("qwen3-4b", "Qwen3-4B"), ("qwen35-9b", "Qwen3.5-9B")]
    segs = [("supported_inapplicable", "Supported but inapplicable", ORANGE, False),
            ("ambiguous_value", "Both values cited; decision fits only the inapplicable one", ORANGE, True),
            ("other", "Arithmetic or reasoning error, other value, unfaithful quote", "#8d8b85", False),
            ("no_answer", "No answer", "#8d8b85", True)]
    fig, axes = plt.subplots(1, len(sets), figsize=(6.6, 2.35 if len(sets) == 1 else 2.6), sharey=True, squeeze=False)
    for ax, (sname, title, q) in zip(axes[0], sets):
        for i, (m, lab) in enumerate(names):
            d = q.get(m) or {}
            a = d.get("audit")
            if not a:
                continue
            n = sum(a["n_per_label"].values())
            t = a["totals"]
            vals = {"supported_inapplicable": t.get("supported_inapplicable", 0), "ambiguous_value": t.get("ambiguous_value", 0),
                    "no_answer": t.get("no_answer", 0),
                    "other": sum(t.get(k, 0) for k in ("numeric_or_reasoning_error", "other_printed_value", "unfaithful_quote"))}
            y = len(names) - 1 - i
            left = 0.0
            for k, label, color, hatched in segs:
                v = vals[k] / n
                if v:
                    ax.barh(y, v, left=left, height=.62, color=SURF if hatched else color, edgecolor=color if hatched else SURF,
                            hatch="////" if hatched else None, lw=1.2, label=label, zorder=2)
                left += v
            ax.text(left + .012, y, f"{sum(vals.values())}/{n} wrong; {vals['supported_inapplicable']} inapplicable", va="center", fontsize=6.6, color=INK)
        ax.set_yticks(range(len(names)), [lab for _, lab in reversed(names)], fontsize=7.8)
        ax.set_xlim(0, .75)
        ax.set_xticks([0, .2, .4, .6], ["0", "20%", "40%", "60%"])
        ax.set_xlabel("Share of cases with a wrong decision", fontsize=7.8)
        ax.set_title(title, fontsize=8.3, loc="left")
        ax.grid(axis="x", color=GRID, lw=.6)
        tidy(ax)
    h, l = axes[0][0].get_legend_handles_labels()
    seen, hh, ll = set(), [], []
    for a_, b_ in zip(h, l):
        if b_ not in seen:
            seen.add(b_); hh.append(a_); ll.append(b_)
    fig.legend(hh, ll, loc="lower center", ncol=2, fontsize=6.6, frameon=False, bbox_to_anchor=(.5, -.01))
    fig.tight_layout(rect=(0, .13, 1, 1), w_pad=.8)
    save(fig, "natural_errors")


if __name__ == "__main__":
    mechanisms()
    natural()
