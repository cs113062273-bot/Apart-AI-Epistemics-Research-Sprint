"""v4: confirmatory replication set, built by the mechanical rule in preregistration/replication.md.

Sources were selected by the pre-registered EDGAR / PubMed procedure (fetch_sources.py): the first 10 eligible companies and the
first 8 eligible abstracts in returned order. For each condition pair (in order of appearance, at most 3 per source):
X = value printed first, Y = the other; A: user condition matches X, limit L = (X+Y)/2; B: matches Y, same L;
C: matches Y, L moved past Y by |X-Y|/2 so that C keeps A's decision. Decisions are 'at least L'. Situations use one fixed
template per domain. Disclosed deviation: the templates were written after the highlights had been screened for pairs
(needed to apply the selection rule) but before any assistant run.
    python data/replication/build.py  ->  data/replication/items.jsonl
"""
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
V4 = HERE.parent / "sources/replication"
ORDER = {c["name"]: c for c in json.load(open(V4 / "finance_order.json", encoding="utf-8"))}


def text(path):
    t = open(path, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def around(t, keys, pad=700):
    idx = [t.index(k) for k in keys]
    lo, hi = max(0, min(idx) - pad), min(len(t), max(i + len(k) for i, k in zip(idx, keys)) + pad)
    while lo > 0 and t[lo] != " ":
        lo -= 1
    while hi < len(t) and t[hi - 1] != " ":
        hi += 1
    return t[lo:hi].strip()


XML = open(V4 / "pubmed_candidates_full.xml", encoding="utf-8").read()


def abstract(pmid):
    art = next(a for a in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", XML, re.S) if re.search(rf"<PMID[^>]*>{pmid}<", a))
    title = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<ArticleTitle>(.*?)</ArticleTitle>", art, re.S).group(1)))
    return title + "\n" + " ".join(html.unescape(re.sub(r"<[^>]+>", "", a)) for a in re.findall(r"<AbstractText[^>]*>.*?</AbstractText>", art, re.S))


def fmt(v, unit):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return {"%": f"{s}%", "pp": f"{s} percentage points", "$M": f"${s} million", "x": f"{s}", "pts": f"{s} points"}[unit]


ITEMS = []


def item(iid, domain, family, source, excerpt, subject, act, metric, unit, X, Y):
    """X, Y = (value, condition phrase, printed snippet). Mechanical A/B/C construction."""
    (xv, xc, xs), (yv, yc, ys) = X, Y
    assert xv != yv, iid
    for s in (xs, ys):
        assert s in excerpt, (iid, s)
    L = (xv + yv) / 2
    Lc = yv - abs(xv - yv) / 2 if xv > yv else yv + abs(xv - yv) / 2
    yes, no = ("passes", "fails") if domain == "finance" else ("yes", "no")
    if domain == "finance":
        ctx = lambda cond, lim: f"I {act} only if {metric} {cond} is at least {fmt(lim, unit)}."
        q = f"Does {subject} pass my screen?"
    else:
        ctx = lambda cond, lim: f"I'll {act} only if {metric} {cond} is at least {fmt(lim, unit)}."
        q = f"Based on this source, does {subject} meet my bar?"
    cases = []
    for label, (val, cond, app, trap, lim) in zip("ABC", [(xv, xc, xs, ys, L), (yv, yc, ys, xs, L), (yv, yc, ys, xs, Lc)]):
        cases.append({"label": label, "context": ctx(cond, lim), "value": val, "limit": round(lim, 4), "direction": "at least",
                      "applicable_text": app, "trap_text": trap, "truth": yes if val >= lim - 1e-9 else no})
    assert cases[1]["truth"] != cases[0]["truth"] and cases[2]["truth"] == cases[0]["truth"], (iid, [c["truth"] for c in cases])
    ITEMS.append({"id": iid, "domain": domain, "family": family, "source": source, "excerpt": excerpt, "subject": subject,
                  "question": q, "decision_options": [yes, no], "split": "v4", "cases": cases})


def fin(name, label):
    c = ORDER[name]
    return text(V4 / c["file"]), [f"{label} 8-K EX-99.1 earnings release (SEC EDGAR)", c["url"]]


GROW = "its latest-quarter {} growth year over year"

# 1 Align
t, src = fin("ALIGN TECHNOLOGY INC", "Align Technology")
ex = around(t, ["Q3'26 operating margin was 16.7%", "Non-GAAP operating margin was 24.4%"])
item("v4-align-gaap", "finance", "gaap_basis", src, ex, "Align Technology", "buy Align Technology", "its Q3'26 operating margin", "%",
     (16.7, "on a GAAP basis", "operating margin was 16.7%"), (24.4, "on a non-GAAP (adjusted) basis", "Non-GAAP operating margin was 24.4%"))
item("v4-align-cc", "finance", "currency_basis", src, ex, "Align Technology", "buy Align Technology", "the year-over-year change in its non-GAAP operating margin", "pts",
     (0.5, "as reported", "up 0.5 points year-over-year"), (1.4, "at constant currency", "up approximately 1.4 points at constant currency"))

# 2 Coupang
t, src = fin("Coupang, Inc.", "Coupang")
ex = around(t, ["Total net revenues were $10.0 billion", "Product Commerce segment net revenues were $8.4 billion"])
item("v4-coupang-cc", "finance", "currency_basis", src, ex, "Coupang", "buy Coupang", GROW.format("total net revenue"), "%",
     (7, "as reported", "up 7% YoY on a reported basis and 11%"), (11, "on a constant currency basis", "11% YoY on a constant currency basis. • Gross profit"))
item("v4-coupang-gp-cc", "finance", "currency_basis", src, ex, "Coupang", "buy Coupang", GROW.format("gross profit"), "%",
     (-6, "as reported", "decreasing 6% YoY on a reported basis"), (-3, "on a constant currency basis", "3% YoY on a constant currency basis"))
item("v4-coupang-segment", "finance", "segment_vs_consolidated", src, ex, "Coupang", "buy Coupang", "the latest-quarter net revenue growth year over year", "%",
     (7, "of the whole company, as reported", "up 7% YoY on a reported basis and 11%"), (5, "of its Product Commerce segment, as reported", "up 5% YoY on a reported basis and 8%"))

# 3 VF
t, src = fin("V F CORP", "VF Corporation")
ex = around(t, ["Operating income (adjusted) ~ $315M", "Americas region remains strong"], pad=500)
item("v4-vf-guidance", "finance", "guidance_vs_reported", src, ex, "VF Corporation", "buy VF Corporation", "its Q2'27 adjusted operating income", "$M",
     (315, "as guided by the company before the quarter", "Operating income (adjusted) ~ $315M"), (364, "as actually reported for the quarter", "$364M Above"))
item("v4-vf-dtc-cc", "finance", "currency_basis", src, ex, "VF Corporation", "buy VF Corporation", "its latest-quarter global DTC revenue growth versus last year", "%",
     (1, "as reported", "+1% vs. LY or +3% C$"), (3, "in constant currency (C$), excluding Dickies", "+3% C$ ex Dickies® ◦ Americas"))
item("v4-vf-americas", "finance", "segment_vs_consolidated", src, ex, "VF Corporation", "buy VF Corporation", "the latest-quarter revenue growth versus last year", "%",
     (-4, "of the whole company, as reported", "Revenue (4%) vs. LY"), (-2, "of its Americas region, as reported", "Americas region remains strong, (2%) vs. LY"))

# 4 CONMED
t, src = fin("CONMED Corp", "CONMED")
ex = around(t, ["Sales of $335.6 million decreased 0.7%", "International sales increased 13.1% as reported"])
item("v4-conmed-cc", "finance", "currency_basis", src, ex, "CONMED", "buy CONMED", GROW.format("sales"), "%",
     (-0.7, "as reported", "decreased 0.7% year-over-year as reported"), (-0.8, "on a constant currency basis", "decreased 0.8% on a constant currency"))
item("v4-conmed-intl-cc", "finance", "currency_basis", src, ex, "CONMED", "buy CONMED", GROW.format("international sales"), "%",
     (13.1, "as reported", "International sales increased 13.1% as reported"), (12.8, "on a constant currency basis", "increased 12.8% on a constant currency"))
item("v4-conmed-segment", "finance", "segment_vs_consolidated", src, ex, "CONMED", "buy CONMED", "the latest-quarter sales growth year over year", "%",
     (-0.7, "of the whole company, as reported", "decreased 0.7% year-over-year as reported"), (13.1, "of its international business, as reported", "International sales increased 13.1% as reported"))

# 5 Ranpak
t, src = fin("Ranpak Holdings Corp.", "Ranpak")
ex = around(t, ["revenue growth of 26.9% year over year", "AEBITDA increased $1.1 million or 5.1%"])
item("v4-ranpak-ytd", "finance", "reporting_period", src, ex, "Ranpak", "buy Ranpak", "Automation revenue growth year over year (constant currency, excluding warrants)", "%",
     (26.9, "for the latest quarter", "revenue growth of 26.9% year over year"), (79.4, "for the year to date", "year-to-date results in Automation up 79.4%"))
item("v4-ranpak-cc", "finance", "currency_basis", src, ex, "Ranpak", "buy Ranpak", GROW.format("net revenue"), "%",
     (2.3, "as reported", "net revenue growth of 2.3%"), (3.4, "on a constant currency basis", "or 3.4% on a constant currency basis"))
item("v4-ranpak-aebitda-cc", "finance", "currency_basis", src, ex, "Ranpak", "buy Ranpak", GROW.format("AEBITDA"), "%",
     (5.1, "as reported", "5.1% to $22.5 million"), (6.1, "on a constant currency basis", "was up 6.1% on a constant currency basis"))

# 6 Fossil
t, src = fin("Fossil Group, Inc.", "Fossil Group")
ex = around(t, ["Net sales totaled $271.2 million", "Wholesale sales in constant currency increased 4.4%"])
item("v4-fossil-cc", "finance", "currency_basis", src, ex, "Fossil Group", "buy Fossil Group", GROW.format("net sales"), "%",
     (0.4, "as reported", "an increase of 0.4% on a reported basis"), (2.0, "in constant currency", "2.0% in constant currency"))
item("v4-fossil-asia", "finance", "segment_vs_consolidated", src, ex, "Fossil Group", "buy Fossil Group", "the latest-quarter net sales growth in constant currency", "%",
     (2.0, "of the whole company", "2.0% in constant currency"), (15.1, "of its Asia region", "Asia net sales increased 15.1%"))
item("v4-fossil-americas", "finance", "segment_vs_consolidated", src, ex, "Fossil Group", "buy Fossil Group", "the latest-quarter net sales growth in constant currency", "%",
     (2.0, "of the whole company", "2.0% in constant currency"), (0.1, "of its Americas region", "the Americas increased 0.1%"))

# 7 Pulmonx
t, src = fin("Pulmonx Corp", "Pulmonx")
ex = around(t, ["Total worldwide revenue in the third quarter of 2026", "Excluding China, international revenue grew 9%"], pad=300)
item("v4-pulmonx-us", "finance", "segment_vs_consolidated", src, ex, "Pulmonx", "buy Pulmonx", "the latest-quarter revenue growth year over year", "%",
     (6, "of the whole company", "a 6% increase from $21.5 million"), (7, "of its U.S. business", "a 7% increase from the third quarter of 2025"))
item("v4-pulmonx-intl-cc", "finance", "currency_basis", src, ex, "Pulmonx", "buy Pulmonx", GROW.format("international revenue"), "%",
     (5, "as reported", "a 5% increase compared to the third quarter of 2025"), (6, "on a constant currency basis", "a 6% increase on a constant currency basis"))
item("v4-pulmonx-intl", "finance", "segment_vs_consolidated", src, ex, "Pulmonx", "buy Pulmonx", "the latest-quarter revenue growth year over year, as reported,", "%",
     (6, "of the whole company", "a 6% increase from $21.5 million"), (5, "of its international business", "a 5% increase compared to the third quarter of 2025"))

# 8 Microsoft
t, src = fin("MICROSOFT CORP", "Microsoft")
ex = around(t, ["Revenue was $92.3 billion", "Non-GAAP results exclude the impact"], pad=300)
item("v4-msft-oi-cc", "finance", "currency_basis", src, ex, "Microsoft", "buy Microsoft", GROW.format("operating income"), "%",
     (21, "as reported", "increased 21% (up 22% in constant currency)"), (22, "in constant currency", "(up 22% in constant currency)"))
item("v4-msft-ni-gaap", "finance", "gaap_basis", src, ex, "Microsoft", "buy Microsoft", GROW.format("net income"), "%",
     (32, "on a GAAP basis", "increased 32% on a GAAP basis, and was $36.4 billion"), (18, "on a non-GAAP basis", "increased 18% (up 19% in constant currency) on a non-GAAP basis • Diluted"))
item("v4-msft-ni-cc", "finance", "currency_basis", src, ex, "Microsoft", "buy Microsoft", "its latest-quarter non-GAAP net income growth year over year", "%",
     (18, "as reported", "increased 18% (up 19% in constant currency) on a non-GAAP basis • Diluted"), (19, "in constant currency", "(up 19% in constant currency) on a non-GAAP basis • Diluted"))

# 9 WEBTOON
t, src = fin("WEBTOON Entertainment Inc.", "WEBTOON Entertainment")
ex = around(t, ["Third Quarter Revenue Decline of 4.0%", "Revenue growth on a constant currency basis in the range of 9.0%-12.0%"], pad=300)
item("v4-webtoon-cc", "finance", "currency_basis", src, ex, "WEBTOON", "buy WEBTOON", GROW.format("revenue"), "%",
     (-4.0, "as reported", "Third Quarter Revenue Decline of 4.0%"), (0.2, "on a constant currency basis", "Revenue Growth on a Constant Currency Basis of 0.2%"))
item("v4-webtoon-guidance", "finance", "guidance_vs_reported", src, ex, "WEBTOON", "buy WEBTOON", "revenue growth on a constant currency basis", "%",
     (0.2, "for the quarter just reported", "Revenue Growth on a Constant Currency Basis of 0.2%"), (9.0, "at the low end of the company's outlook for next quarter", "in the range of 9.0%-12.0%"))

# 10 Alphabet
t, src = fin("Alphabet Inc.", "Alphabet")
ex = around(t, ["Consolidated Alphabet revenues increased 25%", "Google Cloud delivered record growth"], pad=400)
for iid, seg, val, snip in (("v4-alphabet-services", "Google Services", 11, "Google Services revenues increased 11%"),
                            ("v4-alphabet-search", "Google Search & other", 12, "12% growth in Google Search & other"),
                            ("v4-alphabet-cloud", "Google Cloud", 103, "revenues increased 103%")):
    item(iid, "finance", "segment_vs_consolidated", src, ex, "Alphabet", "buy Alphabet", "the latest-quarter revenue growth year over year", "%",
         (25, "of Alphabet as a whole", "Consolidated Alphabet revenues increased 25%"), (val, f"of {seg}", snip))

# ---------------------------------------------------------------- medicine
def med(pmid):
    return abstract(pmid), [f"PubMed {pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"]


ex, src = med("43030285")
item("v4-calcifediol-outcome", "science", "outcome_mismatch", src, ex, "weekly calcifediol", "take weekly calcifediol",
     "the gain over placebo in the share of women reaching", "pp",
     (62.4, "a 25(OH)D level of at least 20 ng/mL", "≥20 ng/mL (68.2% vs. 5.8%"), (21.4, "a 25(OH)D level of at least 30 ng/mL", "≥30 ng/mL (21.4% vs. 0%"))

ex, src = med("43021726")
item("v4-appendix-pp", "science", "analysis_population", src, ex, "oral antibiotics", "switch to oral antibiotics",
     "the reduction in abscess risk versus intravenous antibiotics (negative means oral is worse)", "pp",
     (-1.9, "in the intention-to-treat analysis", "absolute risk difference, 1.9%"), (-1.8, "in the per-protocol analysis", "absolute risk difference, 1.8%"))
item("v4-appendix-outcome", "science", "outcome_mismatch", src, ex, "oral antibiotics", "switch to oral antibiotics",
     "the reduction versus intravenous antibiotics (negative means oral is worse)", "pp",
     (-1.9, "in intra-abdominal abscess", "absolute risk difference, 1.9%"), (-4.7, "in readmission", "increased readmission (difference, 4.7%"))

ex, src = med("43015686")
item("v4-urokinase-lvo", "science", "population_scope", src, ex, "urokinase thrombolysis", "have urokinase thrombolysis",
     "the risk ratio for an excellent 90-day outcome", "x",
     (1.90, "for patients with large vessel occlusion (as I have)", "adjusted risk ratio [RR] 1.90"), (1.02, "for patients without large vessel occlusion (as I have)", "adjusted RR 1.02"))
item("v4-urokinase-mortality", "science", "population_scope", src, ex, "urokinase thrombolysis", "have urokinase thrombolysis",
     "the relative reduction in 90-day mortality (1 minus the risk ratio)", "x",
     (0.96, "for patients with large vessel occlusion (as I have)", "adjusted RR 0.04"), (0.48, "for patients without large vessel occlusion (as I have)", "adjusted RR 0.52"))

ex, src = med("43012849")
item("v4-nepa-emesis", "science", "outcome_mismatch", src, ex, "NEPA", "use NEPA", "the gain over standard care in the rate of", "pp",
     (11.8, "complete response", "(89.1% vs 77.3%"), (12.2, "no emesis", "(92.2% vs 80.0%)"))
item("v4-nepa-nausea", "science", "outcome_mismatch", src, ex, "NEPA", "use NEPA", "the gain over standard care in the rate of", "pp",
     (12.2, "no emesis", "(92.2% vs 80.0%)"), (9.9, "no significant nausea", "(80.6% vs 70.7%)"))

ex, src = med("43004293")
item("v4-dapa-dm", "science", "population_scope", src, ex, "dapagliflozin", "take dapagliflozin after TAVR",
     "the absolute reduction in death or worsening heart failure", "pp",
     (7.5, "for patients with diabetes (as I have)", "(15.2% vs. 22.7%"), (3.0, "for patients without diabetes (as I have)", "(15.0% vs. 18.0%"))

ex, src = med("42983692")
item("v4-chx-ssi", "science", "outcome_mismatch", src, ex, "chlorhexidine vaginal cleansing", "accept chlorhexidine vaginal cleansing",
     "the absolute reduction in", "pp",
     (4.4, "postcesarean endometritis", "(1.9% vs. 6.3%; RR 0.303"), (4.0, "surgical site infection", "(1.4% vs. 5.4%"))
item("v4-chx-wound", "science", "outcome_mismatch", src, ex, "chlorhexidine vaginal cleansing", "accept chlorhexidine vaginal cleansing",
     "the absolute reduction in", "pp",
     (4.0, "surgical site infection", "(1.4% vs. 5.4%"), (7.6, "composite wound complications", "(3.4% vs. 11.0%"))
item("v4-chx-readmission", "science", "outcome_mismatch", src, ex, "chlorhexidine vaginal cleansing", "accept chlorhexidine vaginal cleansing",
     "the absolute reduction in", "pp",
     (7.6, "composite wound complications", "(3.4% vs. 11.0%"), (4.9, "readmission for infection", "readmission for infection (1.4% vs. 6.3%"))

ex, src = med("42975301")
item("v4-cem-outcome", "science", "outcome_mismatch", src, ex, "preoperative contrast-enhanced mammography", "have preoperative contrast-enhanced mammography",
     "the absolute reduction versus control in", "pp",
     (1.0, "the mastectomy rate", "(17% [35 of 202] vs 18% [39 of 213]"), (2.1, "the reoperation rate", "(7.9% [16 of 202] vs 10% [22 of 213]"))

ex, src = med("42957718")
item("v4-reuteri-arr", "science", "relative_vs_absolute", src, ex, "L. reuteri lozenges", "take L. reuteri lozenges during radiotherapy",
     "the reduction in severe oral mucositis", "x",
     (0.39, "relative to the placebo rate (as a fraction, 1 minus the relative risk)", "relative risk 0.61"), (0.238, "in absolute terms (as a fraction of patients)", "absolute risk reduction 23.8 percentage points"))

if __name__ == "__main__":
    with open(HERE / "items.jsonl", "w", encoding="utf-8") as f:
        for it in ITEMS:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(len(ITEMS), "items", sum(len(i["cases"]) for i in ITEMS), "cases",
          {d: sum(i["domain"] == d for i in ITEMS) for d in ("finance", "science")}, "max excerpt", max(len(i["excerpt"]) for i in ITEMS))
