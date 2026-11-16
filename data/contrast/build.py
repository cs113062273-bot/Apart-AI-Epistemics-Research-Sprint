"""Build the Supported-vs-Applicable contrast set from real, verbatim source text.

Each item fixes ONE real source excerpt and ONE faithful claim quoted from it. Only the
user's decision context changes between cases:

  A  the claim's printed condition matches the user's situation  -> answer is right
  B  it does not match, and the applicable printed value flips the recommendation
  C  it does not match, but the recommendation survives (selective-intervention control)

Gold labels are computed from the printed numbers by the arithmetic in `gold()`; no model
is involved. Run once; the output (items.jsonl) is frozen and committed before any method
is run on it. Sources: cached public pricing pages (fetched 2026-11-14/15), SEC EDGAR
8-K EX-99.1 earnings releases, PubMed abstracts (E-utilities).
"""
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE.parent / "sources"

PAGES = {
    "as": ("Asana pricing", "https://asana.com/pricing"), "bc": ("Basecamp pricing", "https://basecamp.com/pricing"),
    "no": ("Notion pricing", "https://www.notion.com/pricing"), "pm": ("Proton Mail pricing", "https://proton.me/mail/pricing"),
    "pv": ("Proton VPN pricing", "https://protonvpn.com/pricing"), "gh": ("GitHub pricing", "https://github.com/pricing"),
    "lo": ("Loom pricing", "https://www.loom.com/pricing"), "tl": ("Tailscale pricing", "https://tailscale.com/pricing"),
    "hz": ("Hetzner Storage Box", "https://www.hetzner.com/storage/storage-box/"),
}


def page_excerpt(tag, keys, before=3, after=3):
    """Verbatim window of line segments around the first segment containing each key."""
    segs = json.load(open(SRC / "pricing" / f"{tag}.json", encoding="utf-8"))["segments"]
    idx = set()
    for key in keys:
        i = next(i for i, s in enumerate(segs) if key in s["text"])
        idx.update(range(max(0, i - before), min(len(segs), i + after + 1)))
    return "\n".join(segs[i]["text"].strip() for i in sorted(idx) if segs[i]["text"].strip())


def release_text(name):
    t = open(SRC / "sec_releases" / f"{name}.htm", encoding="utf-8", errors="ignore").read()
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def release_excerpt(name, keys):
    t = release_text(name)
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z•])", t)
    idx = set()
    for key in keys:
        i = next(i for i, s in enumerate(sents) if key in s)
        idx.update(range(max(0, i - 1), min(len(sents), i + 2)))
    return " ".join(sents[i].strip() for i in sorted(idx))


ABSTRACTS = {}
for art in ET.parse(SRC / "pubmed" / "arr_rrr.xml").getroot().iter("PubmedArticle"):
    pmid = art.findtext(".//PMID")
    title = "".join(art.find(".//ArticleTitle").itertext())
    parts = []
    for a in art.iter("AbstractText"):
        label = a.get("Label")
        parts.append((f"{label}: " if label else "") + "".join(a.itertext()))
    ABSTRACTS[pmid] = (f"{title}\n" + "\n".join(parts)).replace("\xa0", " ")


def money(x, cur="$"):
    return f"{cur}{x:,.2f}".replace(".00", "") if cur != "€" else f"€{x:,.2f}"


ITEMS = []


def add(alt_text=None, **item):
    for key in ("excerpt", "claim"):
        assert item[key].strip(), item["id"]
    if alt_text:
        assert alt_text in item["excerpt"], (item["id"], "applicable value not printed in excerpt", alt_text)
        item["alt_text"] = alt_text
    ITEMS.append(item)


# ---------------------------------------------------------------- procurement: budget decisions
# kind=budget: total = value x seats [x (1+vat)] (or horizon-average for intro prices); fits iff total <= limit.
def budget_period(iid, tag, keys, product, claim_value, alt_value, unit_word, seats, limits, claim_cond, alt_cond, quote):
    a, b, c = limits
    ex = page_excerpt(tag, keys)
    assert quote in ex, (iid, quote)
    claim = f"{product} costs ${claim_value:g} per {unit_word} per month (“{quote}”)."
    seat_txt = f"{seats} {unit_word}s" if seats > 1 else f"1 {unit_word}"
    ctx = [
        ("A", f"We need {seat_txt} and we will pay {claim_cond}. Our hard limit is ${a:g} per month in total.", claim_value, a),
        ("B", f"We need {seat_txt} and we will pay {alt_cond}. Our hard limit is ${b:g} per month in total.", alt_value, b),
        ("C", f"We need {seat_txt} and we will pay {alt_cond}. Our hard limit is ${c:g} per month in total.", alt_value, c),
    ]
    add(alt_text=f"{alt_value:g}", id=iid, domain="procurement", family="billing_period", source=PAGES[tag], excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=t, answer=f"Recommendation: {product} fits your limit. {claim} For {seat_txt} that is ${claim_value * seats:,.2f} per month, within your ${lim:g} limit.",
                    applicable_value=v, total=round(v * seats, 2), limit=lim) for l, t, v, lim in ctx])


budget_period("p-asana-starter", "as", ["$10.99 Per user, per month billed annually. $13.49"], "Asana Starter", 10.99, 13.49, "user", 5,
              (60, 60, 70), "annually", "month to month", "$10.99 Per user, per month billed annually. $13.49 billed monthly")
budget_period("p-asana-advanced", "as", ["$24.99 Per user, per month billed annually. $30.49"], "Asana Advanced", 24.99, 30.49, "user", 4,
              (110, 110, 125), "annually", "month to month", "$24.99 Per user, per month billed annually. $30.49 billed monthly")
budget_period("p-notion-domain", "no", ["custom domain to your Site"], "A Notion custom domain", 8, 10, "domain", 3,
              (25, 25, 32), "annually", "monthly, with no annual commitment", "$8/month/domain paid annually, or $10/month per domain paid monthly")
budget_period("p-basecamp-unlimited", "bc", ["Pro Unlimited", "$329/mo if billed monthly"], "Basecamp Pro Unlimited", 199, 329, "account", 1,
              (250, 250, 350), "annually", "month to month", "Pro Unlimited $199 /mo, billed annually")


def budget_intro(iid, tag, keys, product, first, renew, period_label, limits, quote):
    """Introductory price for the first term, then renewal. Horizon 1 term (A) vs 3 terms (B, C): average per term."""
    a, b, c = limits
    ex = page_excerpt(tag, keys)
    assert quote in ex, (iid, quote)
    claim = f"{product} is billed at ${first:g} per {period_label} (“{quote}”)."
    avg3 = round((first + 2 * renew) / 3, 2)
    ctx = [("A", f"We only need it for one {period_label}. Our hard limit is ${a:g} per {period_label}.", first, a),
           ("B", f"We plan to keep it for three {period_label}s. Our hard limit is ${b:g} per {period_label} on average over that time.", avg3, b),
           ("C", f"We plan to keep it for three {period_label}s. Our hard limit is ${c:g} per {period_label} on average over that time.", avg3, c)]
    add(alt_text=f"{renew:.2f}", id=iid, domain="procurement", family="intro_vs_renewal", source=PAGES[tag], excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=t, answer=f"Recommendation: {product} fits your limit. {claim} That is within your ${lim:g} per {period_label} limit.",
                    applicable_value=v, total=v, limit=lim) for l, t, v, lim in ctx])


budget_intro("p-proton-unlimited", "pm", ["Billed at $77.88 for the first 12 months"], "This Proton plan", 77.88, 119.88, "year", (90, 100, 110),
             "Billed at $77.88 for the first 12 months, then renews at $119.88 every 12 months.")
budget_intro("p-protonvpn-plus", "pv", ["Billed at $35.88 for the first 12 months"], "This Proton VPN plan", 35.88, 83.88, "year", (50, 60, 70),
             "Billed at $35.88 for the first 12 months, then renews at $83.88 every 12 months.")
budget_intro("p-proton-mail", "pm", ["Billed at $29.88 for the first 12 months"], "This Proton Mail plan", 29.88, 47.88, "year", (35, 40, 45),
             "Billed at $29.88 for the first 12 months, then renews at $47.88 every 12 months.")
budget_intro("p-protonvpn-month", "pv", ["$1.00 for the first month"], "This Proton VPN plan", 1.00, 9.99, "month", (5, 5, 8),
             "$1.00 for the first month. Renews at $9.99, cancel anytime.")


def budget_seats(iid, tag, keys, product, price, quote, seats3, limit):
    """Per-user price read as a flat price. A: 1 user; B: enough users to break the limit; C: fewer users that still fit."""
    ex = page_excerpt(tag, keys)
    assert quote in ex, (iid, quote)
    claim = f"{product} costs ${price:g} per user per month (“{quote}”)."
    ctx = [("A", 1), ("B", seats3[1]), ("C", seats3[2])]
    add(alt_text="user" if "user" in quote else "seat", id=iid, domain="procurement", family="per_user", source=PAGES[tag], excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=f"We are a team of {n} {'person' if n == 1 else 'people'}; everyone needs an account. Our hard limit is ${limit:g} per month in total.",
                    answer=f"Recommendation: {product} fits your limit. {claim} That is within your ${limit:g} per month limit.",
                    applicable_value=price, total=round(price * n, 2), limit=limit) for l, n in ctx])


budget_seats("p-github-team", "gh", ["$4 USD per user / month"], "GitHub Team", 4, "$4 USD per user / month", (1, 10, 5), 30)
budget_seats("p-loom-business", "lo", ["$18 per user / month"], "Loom Business", 18, "$18 per user / month", (1, 4, 2), 50)
budget_seats("p-tailscale-standard", "tl", ["$8 Per user, per month"], "Tailscale Standard", 8, "$8 Per user, per month", (1, 5, 2), 20)
budget_seats("p-notion-plus", "no", ["Plus $10 per seat/month"], "Notion Plus", 10, "Plus $10 per seat/month", (1, 3, 2), 25)


def budget_vat(iid, keys, product, net, limits, quote):
    ex = page_excerpt("hz", keys)
    assert quote in ex, (iid, quote)
    claim = f"{product} costs €{net:.2f} per month (“{quote}”)."
    gross = round(net * 1.19, 2)
    a, b, c = limits
    ctx = [("A", f"We are a VAT-registered business and reclaim VAT, so we compare net prices. Our hard limit is €{a:g} per month.", net, a),
           ("B", f"I am a private customer in Germany and pay 19% VAT on top of net prices. My hard limit is €{b:g} per month, all-in.", gross, b),
           ("C", f"I am a private customer in Germany and pay 19% VAT on top of net prices. My hard limit is €{c:g} per month, all-in.", gross, c)]
    add(alt_text="excl. VAT", id=iid, domain="procurement", family="tax_basis", source=PAGES["hz"], excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=t, answer=f"Recommendation: {product} fits your limit. {claim} That is within your €{lim:g} per month limit.",
                    applicable_value=v, total=v, limit=lim) for l, t, v, lim in ctx])


budget_vat("p-hetzner-bx11", ["€ 3.20 per month"], "Hetzner Storage Box BX11", 3.20, (3.5, 3.5, 4), "€ 3.20 per month, excl. VAT")
budget_vat("p-hetzner-bx21", ["€ 10.90 per month"], "Hetzner Storage Box BX21", 10.90, (12, 12, 13.5), "€ 10.90 per month, excl. VAT")


# ---------------------------------------------------------------- finance: screening decisions
# kind=screen: passes iff applicable value >= threshold (direction fixed by the answer's verdict).
def screen(iid, family, name, keys, company, metric, claim_value, claim_cond, alt_value, alt_cond, thresholds, unit, quote, alt_text, verdict="passes"):
    ex = release_excerpt(name, keys)
    assert quote in ex, (iid, quote)
    claim = f"{company}'s {claim_cond} {metric} was {fmt(claim_value, unit)} (“{quote}”)."
    a, b, c = thresholds
    ctx = [("A", f"My screen uses {claim_cond} figures: I only consider companies whose {claim_cond} {metric} is at least {fmt(a, unit)}.", claim_value, a),
           ("B", f"My screen uses {alt_cond} figures: I only consider companies whose {alt_cond} {metric} is at least {fmt(b, unit)}.", alt_value, b),
           ("C", f"My screen uses {alt_cond} figures: I only consider companies whose {alt_cond} {metric} is at least {fmt(c, unit)}.", alt_value, c)]
    add(alt_text=alt_text, id=iid, domain="finance", family=family, source=(f"{company} 8-K EX-99.1 earnings release (SEC EDGAR)", name), excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=t, answer=f"Recommendation: {company} {verdict} your screen. {claim} {'That meets' if verdict == 'passes' else 'That is below'} your {fmt(th, unit)} threshold.",
                    applicable_value=v, threshold=th) for l, t, v, th in ctx])


def fmt(x, unit):
    if unit == "%":
        return f"{x:g}%"
    if unit == "$M":
        return f"${x:,.1f} million" if x >= 0 else f"a loss of ${-x:,.1f} million"
    return f"${x:.2f}"


screen("f-procore-margin", "gaap_basis", "PROCORE_TECHNOLOGIES_INC_", ["GAAP operating margin was (2%)"], "Procore", "operating margin", 23, "non-GAAP", -2, "GAAP",
       (15, 15, -5), "%", "GAAP operating margin was (2%) and non-GAAP operating margin was 23%.", "GAAP operating margin was (2%)")
screen("f-workiva-margin", "gaap_basis", "WORKIVA_INC_", ["Non-GAAP operating margin was 18.3%"], "Workiva", "operating margin", 18.3, "non-GAAP", 6.8, "GAAP",
       (10, 10, 5), "%", "Non-GAAP operating margin was 18.3% compared to 12.7% in the third quarter of 2025.", "GAAP operating margin for the third quarter of 2026 was 6.8%")
screen("f-protolabs-margin", "gaap_basis", "Proto_Labs_Inc_", ["Non-GAAP operating margin was 11.9%"], "Protolabs", "operating margin", 11.9, "non-GAAP", 9.4, "GAAP",
       (10, 10, 9), "%", "Non-GAAP operating margin was 11.9%, up from 10.0% in the third quarter of 2025.", "GAAP operating margin was 9.4%")
screen("f-dexcom-margin", "gaap_basis", "DEXCOM_INC_", ["Non-GAAP operating income* of $339.5 million or 25.3%"], "Dexcom", "operating margin", 25.3, "non-GAAP", 24.3, "GAAP",
       (25, 25, 24), "%", "Non-GAAP operating income* of $339.5 million or 25.3% of reported revenue", "24.3% of revenue")
screen("f-protolabs-eps", "gaap_basis", "Proto_Labs_Inc_", ["Non-GAAP Earnings Per Share of $0.63"], "Protolabs", "earnings per share", 0.63, "non-GAAP", 0.48, "GAAP",
       (0.50, 0.50, 0.45), "$", "Non-GAAP Earnings Per Share of $0.63", "GAAP Earnings Per Share of $0.48")
screen("f-figma-income", "gaap_basis", "Figma_Inc_", ["GAAP net loss was $(81.3) million"], "Figma", "net income", 53.7, "non-GAAP", -81.3, "GAAP",
       (0, 0, -100), "$M", "GAAP net loss was $(81.3) million and non-GAAP net income was $53.7 million.", "GAAP net loss was $(81.3) million")
screen("f-emcor-margin", "reporting_period", "EMCOR_Group_Inc_", ["non-GAAP operating income for the third quarter of 2026 was $579.8 million", "non-GAAP operating income for the first nine months of 2026 was $1.53 billion"], "EMCOR", "non-GAAP operating margin",
       10.5, "third-quarter", 10.0, "first-nine-months", (10.2, 10.2, 9.8), "%",
       "non-GAAP operating income for the third quarter of 2026 was $579.8 million, or 10.5% of revenues.", "or 10.0% of revenues")
screen("f-emcor-income", "reporting_period", "EMCOR_Group_Inc_", ["non-GAAP net income for the third quarter of 2026 was $424.7 million", "non-GAAP net income for the first nine months of 2026 was $1.13 billion"], "EMCOR", "non-GAAP net income",
       424.7, "third-quarter", 1130.0, "first-nine-months", (500, 1000, 1200), "$M",
       "non-GAAP net income for the third quarter of 2026 was $424.7 million", "first nine months of 2026 was $1.13 billion", verdict="fails")


# ---------------------------------------------------------------- science: expected-benefit decisions
def metric_item(iid, pmid, intervention, outcome, population, rrr, arr, thresholds, quote, alt_text):
    ex = ABSTRACTS[pmid]
    assert quote in ex, (iid, quote)
    claim = f"{intervention} reduced the risk of {outcome} by {rrr:g}% (“{quote}”)."
    a, b, c = thresholds
    ctx = [("A", f"I am {population}. I would take it only if it lowers my risk by at least {a:g}% in relative terms.", rrr, a),
           ("B", f"I am {population}. I would take it only if it lowers my risk by at least {b:g} percentage points in absolute terms.", arr, b),
           ("C", f"I am {population}. I would take it only if it lowers my risk by at least {c:g} percentage points in absolute terms.", arr, c)]
    add(alt_text=alt_text, id=iid, domain="science", family="relative_vs_absolute", source=(f"PubMed {pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"), excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label=l, context=t, answer=f"Recommendation: yes, the evidence meets your bar. {claim} That clears your threshold of {th:g}{'%' if l == 'A' else ' percentage points'}.",
                    applicable_value=v, threshold=th) for l, t, v, th in ctx])


metric_item("s-betablocker", "42306649", "β-blocker therapy after myocardial infarction", "death, recurrent MI, or heart failure hospitalization",
            "a patient after a myocardial infarction with an ejection fraction of 45%", 9, 0.9, (5, 2, 0.5),
            "Pooled analysis revealed a 9% relative risk reduction and 0.9% absolute risk reduction", "0.9% absolute risk reduction")
metric_item("s-diabetes-faith", "41114978", "The faith-based lifestyle intervention", "type 2 diabetes over 12 months",
            "an adult in Bangladesh at risk of type 2 diabetes", 42.5, 7.3, (30, 10, 5),
            "a relative risk reduction of 42.5% (95% CI, 15.0%-70.0%)", "absolute risk reduction of 7.3 percentage points")
metric_item("s-eat-mortality", "38320712", "The Eating As Treatment (EAT) intervention", "death over five years",
            "a patient receiving radiotherapy for head and neck cancer", 55, 17, (50, 20, 15),
            "a relative risk reduction of 55% (95% CI, 0.22-0.92)", "absolute risk reduction of 17%")
metric_item("s-sacubitril", "37000983", "Sacubitril-valsartan", "the primary outcome",
            "a patient with heart failure with reduced ejection fraction", 24.3, 3.4, (20, 5, 3),
            "with a relative risk reduction (RRR) of 24.3% and absolute risk reduction (ARR) of 3.4%", "absolute risk reduction (ARR) of 3.4%")


def population_item(iid, pmid, claim_text, quote, match_ctx, mismatch_ctx, bar):
    ex = ABSTRACTS[pmid]
    assert quote in ex, (iid, quote)
    claim = f"{claim_text} (“{quote}”)."
    add(id=iid, domain="science", family="population_scope", source=(f"PubMed {pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"), excerpt=ex, claim=claim, quote=quote,
        cases=[dict(label="A", context=f"{match_ctx} I would use it only if it lowers my risk by at least {bar:g}% in relative terms.", answer=f"Recommendation: yes, the evidence meets your bar. {claim}", population_match=True, threshold=bar),
               dict(label="B", context=f"{mismatch_ctx} I would use it only if it lowers my risk by at least {bar:g}% in relative terms.", answer=f"Recommendation: yes, the evidence meets your bar. {claim}", population_match=False, threshold=bar)])


population_item("s-tirzepatide-age", "41100405", "Among patients 58 years of age or younger, tirzepatide yielded a 60% relative risk reduction for heart failure",
                "among patients ≤ 58 years of age, tirzepatide yielded a 60% relative risk reduction",
                "I am 52 years old with type 2 diabetes and obesity.", "I am 67 years old with type 2 diabetes and obesity.", 30)
population_item("s-nasal-mask-bmi", "40312693", "Anesthetic nasal masks reduced hypoxemia during sedated gastroscopy with a 63% relative risk reduction",
                "Nasal masks significantly reduce hypoxemia (with a 63% relative risk reduction)",
                "I am overweight (BMI 29) and scheduled for a sedated gastroscopy.", "I have a normal weight (BMI 21) and am scheduled for a sedated gastroscopy.", 30)
population_item("s-dexmed-pediatric", "41031209", "Intranasal dexmedetomidine reduced emergence agitation with an 81.8% relative risk reduction",
                "relative risk reduction (RRR), and absolute risk reduction (ARR) of using intranasal DEX in management of EA were 2.77 (95%confidence interval (CI): 1.72-7.19), 81.8%",
                "I am asking for my 6-year-old child who will have general anesthesia.", "I am a 45-year-old adult who will have general anesthesia.", 50)
population_item("s-icosapent-metsyn", "38035037", "Icosapent ethyl use was associated with a 29% relative risk reduction for the first primary composite cardiovascular event",
                "Icosapent ethyl use was associated with a 29% relative risk reduction for the first occurrence of the primary composite endpoint",
                "I have metabolic syndrome and elevated triglycerides while on a statin.", "I do not have metabolic syndrome; I am healthy with normal triglycerides and take no statin.", 20)


# ---------------------------------------------------------------- gold
def gold(item, case):
    """Is the fixed recommendation correct for this user? Pure arithmetic on printed values."""
    if item["family"] == "population_scope":
        return {"answer_correct": case["population_match"], "applies": "yes" if case["population_match"] else "insufficient",
                "correct_recommendation": "yes" if case["population_match"] else "insufficient evidence for this user"}
    if item["domain"] == "procurement":
        fits = case["total"] <= case["limit"] + 1e-9
        return {"answer_correct": fits, "applies": "yes" if case["label"] == "A" else "no",
                "correct_recommendation": "fits" if fits else "does not fit"}
    passes = case["applicable_value"] >= case["threshold"] - 1e-9
    said = "passes" if item["domain"] == "finance" and "fails" not in case["answer"].split(".")[0] else ("yes" if item["domain"] == "science" else "fails")
    if item["domain"] == "finance":
        truth = "passes" if passes else "fails"
        return {"answer_correct": truth == said, "applies": "yes" if case["label"] == "A" else "no", "correct_recommendation": truth}
    truth = "yes" if passes else "no"
    return {"answer_correct": truth == "yes", "applies": "yes" if case["label"] == "A" else "no", "correct_recommendation": truth}


DEV = {"p-asana-starter", "p-github-team", "f-procore-margin", "f-emcor-margin", "s-betablocker", "s-tirzepatide-age"}

rows = []
for item in ITEMS:
    for case in item["cases"]:
        case["gold"] = gold(item, case)
        expect = case["label"] in ("A", "C")
        assert case["gold"]["answer_correct"] == expect, (item["id"], case["label"], case)
    item["split"] = "dev" if item["id"] in DEV else "test"
    rows.append(item)

with open(HERE / "items.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
n_cases = sum(len(r["cases"]) for r in rows)
print(len(rows), "items", n_cases, "cases;", sum(r["split"] == "test" for r in rows), "test items")
