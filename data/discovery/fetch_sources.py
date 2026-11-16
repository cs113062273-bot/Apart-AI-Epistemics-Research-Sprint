"""Fetch the latest earnings-release exhibit (8-K, EX-99.1) for companies never used in v1/v2, from SEC EDGAR.
    python data/discovery/fetch_sources.py
Writes data/sources/sec_releases/<Name>.htm. Generic user agent, one request at a time (well under EDGAR's rate limit).
"""
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parents[1] / "sources/sec_releases"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "DecisionGap-research-script/0.1 research@example.org", "Accept-Encoding": "identity"}
COMPANIES = {"Zoom": 1585521, "Lululemon": 1397187, "Nike": 320187, "Datadog": 1561550, "Garmin": 1121788, "Etsy": 1370637}


def get(url):
    time.sleep(0.4)
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


for name, cik in COMPANIES.items():
    try:
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))["filings"]["recent"]
        for form, acc, items, doc in zip(sub["form"], sub["accessionNumber"], sub["items"], sub["primaryDocument"]):
            if form == "8-K" and "2.02" in items:
                base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
                idx = get(base)
                ex = [h for h in re.findall(r'href="([^"]+\.htm)"', idx) if re.search(r"ex-?99|ex99|exhibit99|dex991", h, re.I)]
                if not ex:
                    continue
                url = ex[0] if ex[0].startswith("http") else "https://www.sec.gov" + ex[0] if ex[0].startswith("/") else base + ex[0]
                html = get(url)
                (OUT / f"{name}.htm").write_text(html, encoding="utf-8")
                print(name, acc, url, len(html))
                break
    except Exception as exc:
        print(name, "failed", repr(exc)[:160])
