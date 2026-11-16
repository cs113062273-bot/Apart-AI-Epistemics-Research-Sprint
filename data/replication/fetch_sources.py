"""v4 source fetch, following preregistration/replication.md.
Finance: EDGAR full-text search results for "constant currency" (taken first, in returned order), then for
"non-GAAP operating margin"; skip companies used in v1-v3 and non-EX-99.1 exhibits; save candidates in order.
Medicine: PubMed esearch with the pre-registered query, in PubMed's order; save abstracts in order.
    python data/replication/fetch_sources.py
"""
import json
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
OUT = HERE.parent / "sources/replication"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "DecisionGap-research-script/0.1 research@example.org", "Accept-Encoding": "identity"}
USED = {"procore", "workiva", "proto labs", "dexcom", "figma", "emcor", "crocs", "hinge health", "adtran", "rci hospitality",
        "zoom", "lululemon", "nike", "datadog", "garmin"}
USED_PMIDS = {"37000983", "38035037", "38320712", "40312693", "41031209", "41100405", "41114978", "42306649", "40931979", "42992175", "42894628"}


def get(url):
    time.sleep(0.4)
    with urlopen(Request(url, headers=UA), timeout=40) as r:
        return r.read().decode("utf-8", errors="replace")


def finance(n_candidates=16):
    order, seen = [], set()
    for q in ("constant currency", "non-GAAP operating margin"):
        d = json.loads(get(f"https://efts.sec.gov/LATEST/search-index?q=%22{quote(q)}%22&forms=8-K&dateRange=custom&startdt=2026-10-01&enddt=2026-11-14"))
        for h in d["hits"]["hits"]:
            s = h["_source"]
            name = s["display_names"][0].split("(")[0].strip()
            if s.get("file_type") != "EX-99.1" or name.lower() in seen or any(u in name.lower() for u in USED):
                continue
            seen.add(name.lower())
            acc, doc = h["_id"].split(":")
            cik = s["ciks"][0].lstrip("0")
            order.append({"name": name, "query": q, "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}", "file_date": s["file_date"]})
    for i, c in enumerate(order[:n_candidates]):
        html = get(c["url"])
        c["file"] = f"{i:02d}_{''.join(ch for ch in c['name'] if ch.isalnum())[:30]}.htm"
        (OUT / c["file"]).write_text(html, encoding="utf-8")
        print(i, c["name"], len(html))
    (OUT / "finance_order.json").write_text(json.dumps(order, indent=1), encoding="utf-8")


def medicine(n=40):
    term = 'randomized controlled trial[pt] AND 2026[dp] AND hasabstract AND ("absolute risk reduction" OR "per-protocol" OR "subgroup" OR "aged")'
    ids = json.loads(get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=200&term=" + quote(term)))["esearchresult"]["idlist"]
    ids = [i for i in ids if i not in USED_PMIDS][:n]
    xml = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=" + ",".join(ids))
    (OUT / "pubmed_candidates.xml").write_text(xml, encoding="utf-8")
    (OUT / "pubmed_order.json").write_text(json.dumps(ids), encoding="utf-8")
    print("pubmed", len(ids))


if __name__ == "__main__":
    finance()
    medicine()
