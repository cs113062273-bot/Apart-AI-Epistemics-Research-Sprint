"""Independent held-out set v2 (built after v1 test results; frozen before any v2 run).

New sources only (none used in v1), longer excerpts, and mostly condition types that NO method was told
about: included quota then overage, minimum billable amount, GiB vs GB, a plan's user cap, brand segment vs
consolidated, constant-currency vs reported growth, guidance vs reported results. Three items reuse v1 types
on new sources. Same A/B/C design and arithmetic gold as v1.
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
GIB = 1.073741824
PAGES = {"sb": ("Supabase pricing", "https://supabase.com/pricing"), "pk": ("Postmark pricing", "https://postmarkapp.com/pricing"),
         "wb": ("Wasabi pricing", "https://wasabi.com/pricing"), "do": ("DigitalOcean Droplet pricing", "https://www.digitalocean.com/pricing/droplets"),
         "bw": ("Bitwarden pricing", "https://bitwarden.com/pricing/"), "sl": ("Slack pricing", "https://slack.com/pricing"),
         "hg": ("Hostinger web hosting pricing", "https://www.hostinger.com/web-hosting")}


def page(tag, keys, before=20, after=20, cap=8000):
    segs = [s["text"].strip() for s in json.load(open(SRC / "pricing" / f"{tag}.json", encoding="utf-8"))["segments"]]
    idx = [next(i for i, s in enumerate(segs) if k in s) for k in keys]
    lo, hi = max(0, min(idx) - before), min(len(segs) - 1, max(idx) + after)
    while len("\n".join(segs[lo:hi + 1])) > cap and hi - lo > max(idx) - min(idx):
        lo, hi = (lo + 1, hi) if min(idx) - lo > hi - max(idx) else (lo, hi - 1)
    return "\n".join(s for s in segs[lo:hi + 1] if s)


def release(name, keys, around=10):
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z•])", B.release_text(name))
    idx = [next(i for i, s in enumerate(sents) if k in s) for k in keys]
    return " ".join(sents[max(0, min(idx) - around):max(idx) + around + 1])


ITEMS = []


def add(iid, domain, family, source, excerpt, claim, quote, needs, cases):
    for t in [quote] + needs:
        assert t in excerpt, (iid, t)
    for c in cases:
        c["gold"] = {"answer_correct": c.pop("ok"), "applies": "yes" if c["label"] == "A" else "no", "correct_recommendation": c.pop("truth")}
        assert c["gold"]["answer_correct"] == (c["label"] in ("A", "C")), (iid, c)
    ITEMS.append({"id": iid, "domain": domain, "family": family, "source": source, "excerpt": excerpt, "claim": claim, "quote": quote,
                  "split": "v2", "cases": cases})


def fits_case(label, context, answer, total, limit, said="fits"):
    ok_val = total <= limit + 1e-9
    truth = "fits" if ok_val else "does not fit"
    return {"label": label, "context": context, "answer": answer, "total": round(total, 2), "limit": limit, "ok": truth == said, "truth": truth}


# ---- included quota, then overage (new type)
def overage(iid, tag, keys, product, base, quote, inc, rate, per, unit, uses, limit, needs):
    ex = page(tag, keys)
    claim = f"{product} costs ${base:g} per month (“{quote}”)."
    ans = f"Recommendation: {product} fits your limit. {claim} That is within your ${limit:g} per month limit."
    cs = []
    for label, use in zip("ABC", uses):
        total = base + max(0, use - inc) / per * rate
        cs.append(fits_case(label, f"We expect about {use:,} {unit} per month. Our hard limit is ${limit:g} per month in total.", ans, total, limit))
    add(iid, "procurement", "quota_overage", PAGES[tag], ex, claim, quote, needs, cs)


overage("v2-supabase-mau", "sb", ["then $0.00325 per MAU"], "Supabase Pro", 25, "$25 / month", 100000, 0.00325, 1, "monthly active users",
        (60000, 110000, 103000), 40, ["100,000 monthly active users", "then $0.00325 per MAU"])
overage("v2-supabase-disk", "sb", ["8 GB disk size per project"], "Supabase Pro", 25, "$25 / month", 8, 0.125, 1, "GB of database disk",
        (5, 60, 40), 30, ["8 GB disk size per project", "then $0.125 per GB"])
overage("v2-postmark-basic", "pk", ["Extra emails @ $1.80 / 1,000"], "Postmark Basic", 15, "$15.00 /mo", 10000, 1.80, 1000, "emails",
        (8000, 15000, 12000), 20, ["Starting at 10,000 emails/month.", "Extra emails @ $1.80 / 1,000"])
overage("v2-postmark-pro", "pk", ["Extra emails @ $1.30 / 1,000"], "Postmark Pro", 16.50, "$16.50 /mo", 10000, 1.30, 1000, "emails",
        (9000, 18000, 15000), 25, ["Extra emails @ $1.30 / 1,000"])

# ---- minimum billable amount (new type)
ex = page("wb", ["Price per TB | $7.99/month", "Minimum monthly charge"])
q = "Price per TB | $7.99/month"
claim = f"Wasabi costs $7.99 per TB per month (“{q}”)."
cs = []
for label, tb, lim in (("A", 3, 30), ("B", 0.4, 5), ("C", 0.4, 9)):
    ans = f"Recommendation: Wasabi fits your limit. {claim} For {tb:g} TB that is ${7.99 * tb:,.2f} per month, within your ${lim:g} limit."
    cs.append(fits_case(label, f"We will store about {tb:g} TB. Our hard limit is ${lim:g} per month.", ans, 7.99 * max(tb, 1), lim))
add("v2-wasabi-minimum", "procurement", "minimum_charge", PAGES["wb"], ex, claim, q, ["Minimum monthly charge | Yes, tied to 1 TB active storage per account"], cs)

# ---- GiB vs GB (new type); the careless answer reads GiB as GB, so it says "does not fit"
ex = page("do", ["4 GiB | 2 vCPUs | 4,000 GiB | 80 GiB"])
q = "4 GiB | 2 vCPUs | 4,000 GiB | 80 GiB | $0.03571 | $24.00"
for iid, what, val, unit_out, needs3, conv in (
        ("v2-do-ssd", "SSD storage", 80, "GB", (90, 85, 88), GIB),
        ("v2-do-transfer", "monthly transfer", 4000, "TB", (4.4, 4.2, 4.3), GIB / 1000)):
    claim = f"The 4 GiB Basic Droplet has {val:,} GiB of {what} (“{q}”)."
    cs = []
    for label, need in zip("ABC", needs3):
        have = val * conv
        truth = "fits" if have >= need - 1e-9 else "does not fit"
        cs.append({"label": label, "context": f"We need at least {need:g} {unit_out} (decimal: 1 {unit_out} = {'10^9' if unit_out == 'GB' else '10^12'} bytes) of {what}.",
                   "answer": f"Recommendation: the 4 GiB Basic Droplet does not fit your requirement. {claim} {val:,} is below your {need:g} {unit_out}.",
                   "have": round(have, 4), "need": need, "ok": truth == "does not fit", "truth": truth})
    add(iid, "procurement", "units_gib_gb", PAGES["do"], ex, claim, q, ["Memory | vCPU | Transfer | SSD | $/hr | $/mo"], cs)

# ---- a plan's user cap (new type)
ex = page("bw", ["Families", "Up to 6 users"])
q = "$3.99 per month"
claim = f"Bitwarden Families costs $3.99 per month (“{q}”)."
ans = f"Recommendation: Bitwarden Families fits your limit. {claim} That is within your $5 per month limit."
cs = []
for label, n in (("A", 4), ("B", 8), ("C", 6)):
    truth = "fits" if n <= 6 and 3.99 <= 5 else "does not fit"
    cs.append({"label": label, "context": f"We are a family of {n}; everyone needs their own account on one plan. Our hard limit is $5 per month.",
               "answer": ans, "people": n, "cap": 6, "ok": truth == "fits", "truth": truth})
add("v2-bitwarden-cap", "procurement", "user_cap", PAGES["bw"], ex, claim, q, ["Up to 6 users", "Billed annually at $47.88"], cs)

# ---- seen types on new sources
ex = page("sl", ["$7.25 USD per user / month, when paying annually"])
q = "$7.25 USD per user / month, when paying annually"
claim = f"Slack Pro costs $7.25 per user per month (“{q}”)."
cs = []
for label, term, lim, price in (("A", "annually", 50, 7.25), ("B", "month to month, at the regular price after any introductory discount", 50, 8.75),
                                ("C", "month to month, at the regular price after any introductory discount", 55, 8.75)):
    ans = f"Recommendation: Slack Pro fits your limit. {claim} For 6 users that is ${7.25 * 6:,.2f} per month, within your ${lim:g} limit."
    cs.append(fits_case(label, f"We need 6 users and we will pay {term}. Our hard limit is ${lim:g} per month in total.", ans, price * 6, lim))
add("v2-slack-period", "procurement", "billing_period", PAGES["sl"], ex, claim, q, ["per user / month, when paying monthly", "$8.75"], cs)

ex = page("hg", ["Today you pay $133.92 for 48 months"])
q = "$2.79 /mo"
claim = f"Hostinger Unlimited costs $2.79 per month (“{q}”)."
cs = []
for label, years, lim in (("A", 4, 3), ("B", 8, 5), ("C", 8, 10)):
    months = years * 12
    avg = 133.92 / 48 if months <= 48 else (133.92 + 16.99 * (months - 48)) / months
    ans = f"Recommendation: Hostinger Unlimited fits your limit. {claim} That is within your ${lim:g} per month limit."
    cs.append(fits_case(label, f"We will keep the hosting for {years} years. Our hard limit is ${lim:g} per month on average over that time.", ans, avg, lim))
add("v2-hostinger-renewal", "procurement", "intro_vs_renewal", PAGES["hg"], ex, claim, q, ["Today you pay $133.92 for 48 months. Renews at $16.99/mo for the same term."], cs)


# ---- finance
def screen2(iid, family, name, keys, claim, quote, needs, said, contexts):
    ex = release(name, keys)
    cs = []
    for label, ctx, value, th in contexts:
        truth = "passes" if value >= th - 1e-9 else "fails"
        cs.append({"label": label, "context": ctx, "answer": f"Recommendation: it {said} your screen. {claim} That {'meets' if said == 'passes' else 'is below'} your {th:g}% threshold.",
                   "applicable_value": value, "threshold": th, "ok": truth == said, "truth": truth})
    add(iid, "finance", family, ("Crocs 8-K EX-99.1 earnings release (SEC EDGAR)" if "Crocs" in name else "Hinge Health 8-K EX-99.1 earnings release (SEC EDGAR)", name),
        ex, claim, quote, needs, cs)


screen2("v2-crocs-segment", "segment_vs_consolidated", "Crocs_Inc_", ["Consolidated revenues were $1,043 million", "HEYDUDE Brand : Revenues increased 6.1%"],
        "HEYDUDE brand revenues increased 6.1% (“HEYDUDE Brand : Revenues increased 6.1% to $170 million”).", "HEYDUDE Brand : Revenues increased 6.1% to $170 million",
        ["Consolidated revenues were $1,043 million, an increase of 4.6%"], "passes",
        [("A", "I am screening the HEYDUDE brand itself: its revenue growth must be at least 5%.", 6.1, 5),
         ("B", "I screen whole companies: Crocs' consolidated revenue growth must be at least 5%.", 4.6, 5),
         ("C", "I screen whole companies: Crocs' consolidated revenue growth must be at least 4%.", 4.6, 4)])
screen2("v2-crocs-wholesale-cc", "currency_basis", "Crocs_Inc_", ["Wholesale revenues grew 1.8%, or 1.9% on a constant currency basis"],
        "Crocs wholesale revenues grew 1.9% on a constant currency basis (“Wholesale revenues grew 1.8%, or 1.9% on a constant currency basis”).",
        "Wholesale revenues grew 1.8%, or 1.9% on a constant currency basis", [], "passes",
        [("A", "My screen uses constant-currency growth: wholesale revenue growth of at least 1.85%.", 1.9, 1.85),
         ("B", "My screen uses reported growth, not currency-adjusted: wholesale revenue growth of at least 1.85%.", 1.8, 1.85),
         ("C", "My screen uses reported growth, not currency-adjusted: wholesale revenue growth of at least 1.5%.", 1.8, 1.5)])
screen2("v2-heydude-wholesale-cc", "currency_basis", "Crocs_Inc_", ["Wholesale revenues increased 14.0% to $79 million"],
        "HEYDUDE wholesale revenues grew 14.1% on a constant currency basis (“Wholesale revenues increased 14.0% to $79 million, or 14.1% on a constant currency basis”).",
        "Wholesale revenues increased 14.0% to $79 million, or 14.1% on a constant currency basis", [], "passes",
        [("A", "My screen uses constant-currency growth: HEYDUDE wholesale growth of at least 14.05%.", 14.1, 14.05),
         ("B", "My screen uses reported growth, not currency-adjusted: HEYDUDE wholesale growth of at least 14.05%.", 14.0, 14.05),
         ("C", "My screen uses reported growth, not currency-adjusted: HEYDUDE wholesale growth of at least 13.5%.", 14.0, 13.5)])
screen2("v2-hinge-guidance", "guidance_vs_reported", "Hinge_Health_Inc_", ["2026 non-GAAP operating margin midpoint raised to 30%", "Non-GAAP operating margin was 33% compared to 20%"],
        "Hinge Health's non-GAAP operating margin is 30% (“2026 non-GAAP operating margin midpoint raised to 30%”).", "2026 non-GAAP operating margin midpoint raised to 30%",
        ["Non-GAAP operating margin was 33% compared to 20% in Q3 2025"], "fails",
        [("A", "My screen uses the company's full-year 2026 guidance: non-GAAP operating margin of at least 32%.", 30, 32),
         ("B", "My screen uses actual reported results for the latest quarter: non-GAAP operating margin of at least 32%.", 33, 32),
         ("C", "My screen uses actual reported results for the latest quarter: non-GAAP operating margin of at least 34%.", 33, 34)])
screen2("v2-hinge-gaap", "gaap_basis", "Hinge_Health_Inc_", ["GAAP operating margin was 21% compared to (4)% in Q3 2025"],
        "Hinge Health's non-GAAP operating margin was 33% (“Non-GAAP operating margin was 33% compared to 20% in Q3 2025”).", "Non-GAAP operating margin was 33% compared to 20% in Q3 2025",
        ["GAAP operating margin was 21%"], "passes",
        [("A", "My screen uses non-GAAP figures: operating margin of at least 25%.", 33, 25),
         ("B", "My screen uses GAAP figures: operating margin of at least 25%.", 21, 25),
         ("C", "My screen uses GAAP figures: operating margin of at least 20%.", 21, 20)])

with open(HERE / "items.jsonl", "w", encoding="utf-8") as f:
    for r in ITEMS:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(ITEMS), "items", sum(len(i["cases"]) for i in ITEMS), "cases; mean excerpt chars", sum(len(i["excerpt"]) for i in ITEMS) // len(ITEMS))
