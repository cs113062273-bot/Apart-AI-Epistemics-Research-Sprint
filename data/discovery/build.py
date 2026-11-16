"""v3: natural-answer set (built after the v2 run; frozen before any assistant or verifier ran on it).

Sources never used in any earlier item or prompt: five SEC 8-K earnings releases fetched for v3 (Zoom, Lululemon, Nike,
Datadog, Garmin), two releases downloaded during v2 construction but never used (ADTRAN, RCI), and three PubMed abstracts
from the earlier download files that no item used. Each item fixes an excerpt, a decision question and three user
situations (A: the headline value's condition holds; B: it does not and the applicable printed value flips the decision;
C: it does not but the decision survives). Unlike v1/v2 there is no templated answer: assistants write the answers.
Each case records the printed value that applies to the user and the printed 'trap' value whose condition does not,
so a natural answer's error can be typed automatically. Gold decisions follow from printed numbers by arithmetic.
    python data/discovery/build.py   ->  data/discovery/items.jsonl
"""
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE.parent / "sources"


def text(path):
    t = open(path, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def window(t, start, end):
    i = t.index(start)
    j = t.index(end, i) + len(end)
    return t[i:j]


def abstract(xml, pmid):
    x = open(SRC / "pubmed" / xml, encoding="utf-8").read()
    art = next(a for a in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", x, re.S) if re.search(rf"<PMID[^>]*>{pmid}<", a))
    title = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<ArticleTitle>(.*?)</ArticleTitle>", art, re.S).group(1)))
    parts = [html.unescape(re.sub(r"<[^>]+>", "", a)) for a in re.findall(r"<AbstractText[^>]*>.*?</AbstractText>", art, re.S)]
    return title + "\n" + " ".join(parts)


ITEMS = []


def add(iid, domain, family, source, excerpt, subject, question, cases, needs):
    for t in needs:
        assert t in excerpt, (iid, t)
    yes, no = ("passes", "fails") if domain == "finance" else ("yes", "no")
    out = []
    for label, context, value, limit, direction, applicable, trap in cases:
        ok = value >= limit - 1e-9 if direction == "at least" else value <= limit + 1e-9
        for v in (applicable, trap):
            assert v in excerpt, (iid, label, v)
        out.append({"label": label, "context": context, "value": value, "limit": limit, "direction": direction,
                    "applicable_text": applicable, "trap_text": trap, "truth": yes if ok else no})
    # design check: A and C keep the headline-value decision, B flips it
    head = out[0]["truth"]
    assert out[1]["truth"] != head and out[2]["truth"] == head, (iid, [c["truth"] for c in out])
    ITEMS.append({"id": iid, "domain": domain, "family": family, "source": source, "excerpt": excerpt, "subject": subject,
                  "question": question, "decision_options": [yes, no], "split": "v3", "cases": out})


# ---------------------------------------------------------------- finance (screens; decision = passes / fails)
Z = text(SRC / "sec_releases/Zoom.htm")
zx = window(Z, "Second Quarter Fiscal Year 2027 Financial Highlights", "or $1.55 per share.")
zsrc = ["Zoom 8-K EX-99.1 earnings release (SEC EDGAR)", "https://www.sec.gov/Archives/edgar/data/1585521/000158552126000119/zm-20260731ex991.htm"]
add("v3-zoom-gaap", "finance", "gaap_basis", zsrc, zx, "Zoom", "Does Zoom pass my screen?", [
    ("A", "I screen software stocks on adjusted (non-GAAP) operating margin for the latest quarter and only buy if it is at least 30%.", 40.0, 30, "at least", "non-GAAP operating margin was 40.0%", "GAAP operating margin was 24.6%"),
    ("B", "I screen software stocks on GAAP operating margin for the latest quarter and only buy if it is at least 30%.", 24.6, 30, "at least", "GAAP operating margin was 24.6%", "non-GAAP operating margin was 40.0%"),
    ("C", "I screen software stocks on GAAP operating margin for the latest quarter and only buy if it is at least 20%.", 24.6, 20, "at least", "GAAP operating margin was 24.6%", "non-GAAP operating margin was 40.0%")],
    ["GAAP operating margin was 24.6% and non-GAAP operating margin was 40.0%"])
add("v3-zoom-cc", "finance", "currency_basis", zsrc, zx, "Zoom", "Does Zoom pass my screen?", [
    ("A", "I only buy if latest-quarter revenue grew at least 4.8% year over year, as reported.", 4.9, 4.8, "at least", "up 4.9% year over year", "up 4.7% year over year"),
    ("B", "I only buy if latest-quarter revenue grew at least 4.8% year over year in constant currency, so exchange rates don't flatter the number.", 4.7, 4.8, "at least", "up 4.7% year over year", "up 4.9% year over year"),
    ("C", "I only buy if latest-quarter revenue grew at least 4.5% year over year in constant currency, so exchange rates don't flatter the number.", 4.7, 4.5, "at least", "up 4.7% year over year", "up 4.9% year over year")],
    ["Total revenue for the second quarter was $1,277.2 million, up 4.9% year over year", "revenue in constant currency was $1,274.5 million, up 4.7% year over year"])

L = text(SRC / "sec_releases/Lululemon.htm")
lx = window(L, "For the second quarter of 2026, compared to the second quarter of 2025:", "operating margin decreased 190 basis points to 18.8%.")
lsrc = ["Lululemon 8-K EX-99.1 earnings release (SEC EDGAR)", "https://www.sec.gov/Archives/edgar/data/1397187/000139718726000126/lulu-20260802xex991.htm"]
add("v3-lulu-cd", "finance", "currency_basis", lsrc, lx, "Lululemon", "Does Lululemon pass my screen?", [
    ("A", "I hold retailers only if latest-quarter net revenue fell no more than 4.5% year over year, as reported.", -4, -4.5, "at least", "Net revenue decreased 4%", "decreased 5% on a constant dollar basis"),
    ("B", "I hold retailers only if latest-quarter net revenue fell no more than 4.5% year over year on a constant dollar basis.", -5, -4.5, "at least", "decreased 5% on a constant dollar basis", "Net revenue decreased 4%"),
    ("C", "I hold retailers only if latest-quarter net revenue fell no more than 6% year over year on a constant dollar basis.", -5, -6, "at least", "decreased 5% on a constant dollar basis", "Net revenue decreased 4%")],
    ["Net revenue decreased 4% to $2.4 billion, or decreased 5% on a constant dollar basis"])
add("v3-lulu-americas", "finance", "segment_vs_consolidated", lsrc, lx, "Lululemon", "Does Lululemon pass my screen?", [
    ("A", "I hold Lululemon only if company-wide net revenue fell no more than 6% year over year in the latest quarter.", -4, -6, "at least", "Net revenue decreased 4%", "Americas net revenue decreased 8%"),
    ("B", "My thesis is about its Americas business: I hold only if Americas net revenue fell no more than 6% year over year in the latest quarter.", -8, -6, "at least", "Americas net revenue decreased 8%", "Net revenue decreased 4%"),
    ("C", "My thesis is about its Americas business: I hold only if Americas net revenue fell no more than 10% year over year in the latest quarter.", -8, -10, "at least", "Americas net revenue decreased 8%", "Net revenue decreased 4%")],
    ["Americas net revenue decreased 8%"])

N = text(SRC / "sec_releases/Nike.htm")
nx = window(N, "Overall Results", "Revenues for Converse were $263 million")
nsrc = ["Nike 8-K EX-99.1 earnings release (SEC EDGAR)", "https://www.sec.gov/Archives/edgar/data/320187/000032018726000184/q1fy27exhibit991er.htm"]
add("v3-nike-direct", "finance", "currency_basis", nsrc, nx, "Nike", "Does Nike pass my screen?", [
    ("A", "I track NIKE Direct and stay invested only if its revenue fell no more than 8.5% year over year last quarter, as reported.", -8, -8.5, "at least", "down 8 percent on a reported basis and down 9 percent on a currency-neutral basis, due to a 13 percent", "down 9 percent on a currency-neutral basis, due to a 13 percent"),
    ("B", "I track NIKE Direct and stay invested only if its revenue fell no more than 8.5% year over year last quarter on a currency-neutral basis.", -9, -8.5, "at least", "down 9 percent on a currency-neutral basis, due to a 13 percent", "down 8 percent on a reported basis and down 9 percent on a currency-neutral basis, due to a 13 percent"),
    ("C", "I track NIKE Direct and stay invested only if its revenue fell no more than 10% year over year last quarter on a currency-neutral basis.", -9, -10, "at least", "down 9 percent on a currency-neutral basis, due to a 13 percent", "down 8 percent on a reported basis and down 9 percent on a currency-neutral basis, due to a 13 percent")],
    ["NIKE Direct revenues were $4.1 billion, down 8 percent on a reported basis and down 9 percent on a currency-neutral basis"])

D = text(SRC / "sec_releases/Datadog.htm")
dx = window(D, "Third Quarter 2026 Financial Highlights:", "assuming approximately 375 million weighted average diluted shares outstanding.")
dsrc = ["Datadog 8-K EX-99.1 earnings release (SEC EDGAR)", "https://www.sec.gov/Archives/edgar/data/1561550/000162828026069792/ex-991x20260930x8k.htm"]
add("v3-datadog-eps", "finance", "gaap_basis", dsrc, dx, "Datadog", "Does Datadog pass my screen?", [
    ("A", "I use adjusted (non-GAAP) diluted EPS: I buy only if the latest quarter's figure is at least $0.50.", 0.81, 0.50, "at least", "non-GAAP net income per diluted share was $0.81", "GAAP net income per diluted share was $0.32"),
    ("B", "I use GAAP diluted EPS: I buy only if the latest quarter's figure is at least $0.50.", 0.32, 0.50, "at least", "GAAP net income per diluted share was $0.32", "non-GAAP net income per diluted share was $0.81"),
    ("C", "I use GAAP diluted EPS: I buy only if the latest quarter's figure is at least $0.25.", 0.32, 0.25, "at least", "GAAP net income per diluted share was $0.32", "non-GAAP net income per diluted share was $0.81")],
    ["GAAP net income per diluted share was $0.32; non-GAAP net income per diluted share was $0.81"])
add("v3-datadog-guidance", "finance", "guidance_vs_reported", dsrc, dx, "Datadog", "Does Datadog pass my screen?", [
    ("A", "I buy only if non-GAAP net income per diluted share for the quarter just reported was at least $0.75.", 0.81, 0.75, "at least", "non-GAAP net income per diluted share was $0.81", "Non-GAAP net income per share between $0.69 and $0.71"),
    ("B", "I look forward: I buy only if the low end of the company's outlook for next quarter's non-GAAP net income per share is at least $0.75.", 0.69, 0.75, "at least", "Non-GAAP net income per share between $0.69 and $0.71", "non-GAAP net income per diluted share was $0.81"),
    ("C", "I look forward: I buy only if the low end of the company's outlook for next quarter's non-GAAP net income per share is at least $0.65.", 0.69, 0.65, "at least", "Non-GAAP net income per share between $0.69 and $0.71", "non-GAAP net income per diluted share was $0.81")],
    ["Fourth Quarter 2026 Outlook: ◦ Revenue between $1.19 billion and $1.20 billion."])

G = text(SRC / "sec_releases/Garmin.htm")
gx = window(G, "Highlights include:", "Pro forma diluted EPS (1) $ 2.76 $ 1.99 39% $ 7.65 $ 5.77 33%")
gx += " " + window(G, "Fitness: Revenue from the fitness segment increased 16%", "primarily due to domain controllers.")
gsrc = ["Garmin 8-K EX-99.1 earnings release (SEC EDGAR)", "https://www.sec.gov/Archives/edgar/data/1121788/000119312526435066/grmn-ex99_1.htm"]
add("v3-garmin-auto", "finance", "segment_vs_consolidated", gsrc, gx, "Garmin", "Does Garmin pass my screen?", [
    ("A", "I hold Garmin only if company-wide revenue grew year over year in the latest quarter (growth of at least 0%).", 12, 0, "at least", "a 12% increase compared to the prior year quarter", "auto OEM segment decreased 20%"),
    ("B", "I hold Garmin for its car business: only if Auto OEM segment revenue grew year over year in the latest quarter (growth of at least 0%).", -20, 0, "at least", "auto OEM segment decreased 20%", "a 12% increase compared to the prior year quarter"),
    ("C", "I hold Garmin for its car business: only if Auto OEM segment revenue fell no more than 25% year over year in the latest quarter.", -20, -25, "at least", "auto OEM segment decreased 20%", "a 12% increase compared to the prior year quarter")],
    ["Record consolidated revenue of $1.99 billion, a 12% increase compared to the prior year quarter"])
add("v3-garmin-ytd", "finance", "reporting_period", gsrc, gx, "Garmin", "Does Garmin pass my screen?", [
    ("A", "I care about Garmin's outdoor segment: I hold only if its revenue grew at least 10% year over year in the latest quarter.", 20, 10, "at least", "outdoor segment increased 20%", "Outdoor 597,301 497,598 20% 1,497,571 1,426,451 5%"),
    ("B", "I care about Garmin's outdoor segment: I hold only if its revenue grew at least 10% year over year for the year to date (the first 39 weeks).", 5, 10, "at least", "Outdoor 597,301 497,598 20% 1,497,571 1,426,451 5%", "outdoor segment increased 20%"),
    ("C", "I care about Garmin's outdoor segment: I hold only if its revenue grew at least 3% year over year for the year to date (the first 39 weeks).", 5, 3, "at least", "Outdoor 597,301 497,598 20% 1,497,571 1,426,451 5%", "outdoor segment increased 20%")],
    ["13-Weeks Ended 39-Weeks Ended"])

A = text(SRC / "sec_releases/ADTRAN_Holdings_Inc_.htm")
ax = window(A, "today announced its unaudited financial results for the third quarter ended September 30, 2026.", "timing of large customer projects.")
asrc = ["ADTRAN 8-K EX-99.1 earnings release (SEC EDGAR)", "ADTRAN Holdings 8-K EX-99.1, Q3 2026 results"]
add("v3-adtran-gaap", "finance", "gaap_basis", asrc, ax, "ADTRAN", "Does ADTRAN pass my screen?", [
    ("A", "I use non-GAAP operating margin: I buy only if the latest quarter's figure is at least 2%.", 5.0, 2, "at least", "non-GAAP operating margin of 5.0%", "GAAP operating margin of -0.3%"),
    ("B", "I use GAAP operating margin: I buy only if the latest quarter's figure is at least 2%.", -0.3, 2, "at least", "GAAP operating margin of -0.3%", "non-GAAP operating margin of 5.0%"),
    ("C", "I use GAAP operating margin: I buy only if the latest quarter's figure is at least -1%, i.e. roughly break-even or better.", -0.3, -1, "at least", "GAAP operating margin of -0.3%", "non-GAAP operating margin of 5.0%")],
    ["GAAP operating margin of -0.3%; non-GAAP operating margin of 5.0%"])
add("v3-adtran-guidance", "finance", "guidance_vs_reported", asrc, ax, "ADTRAN", "Does ADTRAN pass my screen?", [
    ("A", "I buy only if the non-GAAP operating margin for the quarter just reported was at least 3%.", 5.0, 3, "at least", "non-GAAP operating margin of 5.0%", "within a range of 1.0% to 5.0%"),
    ("B", "I look forward: I buy only if the low end of the company's outlook for next quarter's non-GAAP operating margin is at least 3%.", 1.0, 3, "at least", "within a range of 1.0% to 5.0%", "non-GAAP operating margin of 5.0%"),
    ("C", "I look forward: I buy only if the low end of the company's outlook for next quarter's non-GAAP operating margin is at least 0.5%.", 1.0, 0.5, "at least", "within a range of 1.0% to 5.0%", "non-GAAP operating margin of 5.0%")],
    ["For the fourth quarter of 2026"])

R = text(SRC / "sec_releases/RCI_HOSPITALITY_HOLDINGS_INC_.htm")
rx = window(R, "3Q26 Results (Comparisons are to year-ago periods unless indicated otherwise)", "or 7.4% of segment revenues compared to 0.9%.")
rsrc = ["RCI Hospitality 8-K EX-99.1 earnings release (SEC EDGAR)", "RCI Hospitality Holdings 8-K EX-99.1, 3Q26 results"]
add("v3-rci-gaap", "finance", "gaap_basis", rsrc, rx, "RCI's Nightclubs segment", "Does RCI's Nightclubs segment pass my screen?", [
    ("A", "I judge RCI's Nightclubs segment on non-GAAP operating margin (operating income as a share of segment revenues): it must be at least 31.5% this quarter.", 32.1, 31.5, "at least", "32.1% of segment revenues", "31.2% of segment revenues"),
    ("B", "I judge RCI's Nightclubs segment on GAAP operating margin (operating income as a share of segment revenues): it must be at least 31.5% this quarter.", 31.2, 31.5, "at least", "31.2% of segment revenues", "32.1% of segment revenues"),
    ("C", "I judge RCI's Nightclubs segment on GAAP operating margin (operating income as a share of segment revenues): it must be at least 30% this quarter.", 31.2, 30, "at least", "31.2% of segment revenues", "32.1% of segment revenues")],
    ["Operating income was $19.6 million compared to $17.9 million or 31.2% of segment revenues compared to 28.6%."])

# ---------------------------------------------------------------- medicine (decision = yes / no)
P = abstract("arr_rrr.xml", "40931979")
psrc = ["PubMed 40931979", "https://pubmed.ncbi.nlm.nih.gov/40931979/"]
add("v3-probiotics-arr", "science", "relative_vs_absolute", psrc, P, "probiotics",
    "Based on this source, does taking probiotics meet my bar?", [
    ("A", "I'm starting antibiotics. I'll take probiotics only if they cut my risk of C difficile-associated diarrhea by at least 30% relative to my baseline risk.", 50, 30, "at least", "relative risk reduction (RRR) of 50%", "absolute risk reduction (ARR) of 1.6%"),
    ("B", "I'm starting antibiotics. I'll take probiotics only if they cut my risk of C difficile-associated diarrhea by at least 2 percentage points in absolute terms.", 1.6, 2, "at least", "absolute risk reduction (ARR) of 1.6%", "relative risk reduction (RRR) of 50%"),
    ("C", "I'm starting antibiotics. I'll take probiotics only if they cut my risk of C difficile-associated diarrhea by at least 1 percentage point in absolute terms.", 1.6, 1, "at least", "absolute risk reduction (ARR) of 1.6%", "relative risk reduction (RRR) of 50%")],
    ["in incidence of CDAD"])
add("v3-probiotics-outcome", "science", "outcome_mismatch", psrc, P, "probiotics",
    "Based on this source, does taking probiotics meet my bar?", [
    ("A", "I'm starting antibiotics. What I care about is carrying C difficile in my stool (colonization); I'll take probiotics only if they cut that by at least 2 percentage points in absolute terms.", 2.1, 2, "at least", "(ARR 2.1%;", "absolute risk reduction (ARR) of 1.6%"),
    ("B", "I'm starting antibiotics. What I care about is getting C difficile-associated diarrhea; I'll take probiotics only if they cut that by at least 2 percentage points in absolute terms.", 1.6, 2, "at least", "absolute risk reduction (ARR) of 1.6%", "(ARR 2.1%;"),
    ("C", "I'm starting antibiotics. What I care about is getting C difficile-associated diarrhea; I'll take probiotics only if they cut that by at least 1.5 percentage points in absolute terms.", 1.6, 1.5, "at least", "absolute risk reduction (ARR) of 1.6%", "(ARR 2.1%;")],
    ["colonization in absence of symptoms"])

T = abstract("arr_rrr.xml", "42992175")
tsrc = ["PubMed 42992175", "https://pubmed.ncbi.nlm.nih.gov/42992175/"]
q = "Based on this source, does choosing conjunctival autograft over amniotic membrane transplantation meet my bar?"
add("v3-pterygium-arr", "science", "relative_vs_absolute", tsrc, T, "conjunctival autograft", q, [
    ("A", "I need pterygium surgery. I'll choose conjunctival autograft only if it lowers recurrence by at least 40% relative to amniotic membrane.", 44.1, 40, "at least", "RRR of 44.1%", "ARR of 6.5% points"),
    ("B", "I need pterygium surgery. I'll choose conjunctival autograft only if it lowers my recurrence risk by at least 10 percentage points in absolute terms.", 6.5, 10, "at least", "ARR of 6.5% points", "RRR of 44.1%"),
    ("C", "I need pterygium surgery. I'll choose conjunctival autograft only if it lowers my recurrence risk by at least 5 percentage points in absolute terms.", 6.5, 5, "at least", "ARR of 6.5% points", "RRR of 44.1%")],
    ["Recurrence was lower with CAG than AMT (8.3% vs 14.8%"])
add("v3-pterygium-age", "science", "population_scope", tsrc, T, "conjunctival autograft", q, [
    ("A", "I'm 35 and need pterygium surgery. I'll choose conjunctival autograft only if, for patients like me, it lowers recurrence by at least 3 percentage points.", 21.1, 3, "at least", "0% (0/54) with CAG vs 21.1% (15/71) with AMT in patients aged 20-40 years", "(11.1% vs 11.5%)"),
    ("B", "I'm 50 and need pterygium surgery. I'll choose conjunctival autograft only if, for patients like me, it lowers recurrence by at least 3 percentage points.", 0.4, 3, "at least", "(11.1% vs 11.5%)", "ARR of 6.5% points"),
    ("C", "I'm 50 and need pterygium surgery. I'll choose conjunctival autograft if, for patients like me, it lowers recurrence at all (by more than 0 percentage points).", 0.4, 0.01, "at least", "(11.1% vs 11.5%)", "ARR of 6.5% points")],
    ["in patients aged 41-60 years"])

E = abstract("pp_itt.xml", "42894628")
esrc = ["PubMed 42894628", "https://pubmed.ncbi.nlm.nih.gov/42894628/"]
add("v3-esketamine-pp", "science", "analysis_population", esrc, E, "esketamine",
    "Based on this source, does esketamine meet my bar?", [
    ("A", "For my clinic's protocol decision, I count every randomized patient (intention-to-treat): esketamine must lower sleep disturbance on day 3 by at least 11.6 percentage points.", 11.84, 11.6, "at least", "risk difference, -11.84 percentage points", "(12.8% vs 24.2%"),
    ("B", "I want the effect in patients who actually received the treatment as planned (per-protocol): esketamine must lower sleep disturbance on day 3 by at least 11.6 percentage points.", 11.4, 11.6, "at least", "(12.8% vs 24.2%", "risk difference, -11.84 percentage points"),
    ("C", "I want the effect in patients who actually received the treatment as planned (per-protocol): esketamine must lower sleep disturbance on day 3 by at least 11 percentage points.", 11.4, 11, "at least", "(12.8% vs 24.2%", "risk difference, -11.84 percentage points")],
    ["The per-protocol (PP) sensitivity analysis yielded similar results"])

if __name__ == "__main__":
    with open(HERE / "items.jsonl", "w", encoding="utf-8") as f:
        for it in ITEMS:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(len(ITEMS), "items", sum(len(i["cases"]) for i in ITEMS), "cases",
          {d: sum(i["domain"] == d for i in ITEMS) for d in ("finance", "science")},
          "max excerpt", max(len(i["excerpt"]) for i in ITEMS))
