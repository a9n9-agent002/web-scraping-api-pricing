#!/usr/bin/env python3
"""Recompute every number quoted in README.md from prices.json and fail on any drift."""
import json
import os
import re
import sys

import cost as c

HERE = os.path.dirname(os.path.abspath(__file__))
README = open(os.path.join(HERE, "README.md")).read()
FLAT = " ".join(README.split())
D = c.load()
P = D["providers"]
fails = []
checks = 0


def eq(label, got, want, tol=0.005):
    global checks
    checks += 1
    if abs(got - want) > tol:
        fails.append("%s: computed %.4f, README says %.4f" % (label, got, want))


def has(label, text):
    global checks
    checks += 1
    if text not in FLAT:
        fails.append("%s: README is missing %r" % (label, text))


def has_raw(label, text):
    global checks
    checks += 1
    if text not in README:
        fails.append("%s: README is missing %r" % (label, text))


def per1000(name, pages, kind):
    if name == "jina_reader":
        return c.jina_cost(D)[0]["median"]
    v = c.block_cost(P[name], pages, kind)
    return None if v is None else v[2]


# --- the three printed tables: each row must appear in the README verbatim ---------------
for kind in ("basic", "render", "json"):
    names = c.KIND_PROVIDERS[kind]
    for pages in c.VOLUMES:
        row = c.cells(D, kind, pages)
        rendered = "%-12d" % pages + "".join(
            "%16s" % ("--" if row[n] is None else ("%.2f" % row[n])) for n in names)
        has_raw("table %s/%d" % (kind, pages), rendered)

# --- finding 1: the one-page cliffs -----------------------------------------------------
eq("firecrawl 5,000 basic", per1000("firecrawl", 5000, "basic"), 3.80)
eq("firecrawl 5,001 basic", per1000("firecrawl", 5001, "basic"), 19.80)
eq("firecrawl cliff ratio", per1000("firecrawl", 5001, "basic") / per1000("firecrawl", 5000, "basic"), 5.2, tol=0.06)
eq("firecrawl cliff dollars", c.block_cost(P["firecrawl"], 5001, "basic")[1] - 19, 80, tol=0.01)
eq("scrapingbee 75,000 basic", per1000("scrapingbee", 75000, "basic"), 0.25)
eq("scrapingbee 75,001 basic", per1000("scrapingbee", 75001, "basic"), 0.65)
eq("scrapingbee cliff ratio", per1000("scrapingbee", 75001, "basic") / per1000("scrapingbee", 75000, "basic"), 2.6, tol=0.06)
eq("scrapingbee cliff dollars", c.block_cost(P["scrapingbee"], 75001, "basic")[1] - 19, 30, tol=0.01)

# --- finding 2: the JSON multiplier hides in the block ----------------------------------
eq("json 20,000 pages", per1000("firecrawl", 20000, "json"), 4.95)
eq("basic 20,000 pages", per1000("firecrawl", 20000, "basic"), 4.95)
eq("json/basic at 20,000", per1000("firecrawl", 20000, "json") / per1000("firecrawl", 20000, "basic"), 1.00)
eq("json 20,001 pages", per1000("firecrawl", 20001, "json"), 19.95)
eq("json/basic at 20,001", per1000("firecrawl", 20001, "json") / per1000("firecrawl", 20001, "basic"), 4.03, tol=0.01)
eq("json 100,000 pages", per1000("firecrawl", 100000, "json"), 3.99)
eq("json/basic at 100,000", per1000("firecrawl", 100000, "json") / per1000("firecrawl", 100000, "basic"), 4.03, tol=0.01)
eq("json credits per page", P["firecrawl"]["credits_per_page"]["json"], 5, tol=0)
eq("json extra credits", P["firecrawl"]["credits_per_page"]["json"] - 1, 4, tol=0)

# --- finding 3: jina is a range --------------------------------------------------------
j = c.jina_cost(D)[0]
eq("jina per 1,000 low", j["low"], 0.13)
eq("jina per 1,000 median", j["median"], 0.27)
eq("jina per 1,000 high", j["high"], 0.63)
eq("jina spread", j["high"] / j["low"], 5.0, tol=0.1)
for m in P["jina_reader"]["measured_tokens_per_page"]:
    eq("jina tokens %s" % m["url"], round(m["tokens"] * P["jina_reader"]["usd_per_1m_tokens"] / 1e6, 6),
       round(m["tokens"] * 0.05 / 1e6, 6), tol=1e-9)

# --- the opening claim and the closing picks ------------------------------------------
for label, name, pages, want in [
    ("1,000 pages firecrawl", "firecrawl", 1000, 0.00),
    ("1,000 pages tavily", "tavily", 1000, 0.00),
    ("1,000 pages crawl4ai", "crawl4ai_cloud", 1000, 10.00),
    ("1,000 pages scrapingbee", "scrapingbee", 1000, 19.00),
    ("100,000 pages jina", "jina_reader", 100000, 0.27),
    ("100,000 pages scrapingbee", "scrapingbee", 100000, 0.49),
    ("100,000 pages crawl4ai", "crawl4ai_cloud", 100000, 0.82),
    ("100,000 pages firecrawl", "firecrawl", 100000, 0.99),
    ("100,000 pages tavily", "tavily", 100000, 2.20),
    ("crawl4ai 10,000 pages", "crawl4ai_cloud", 10000, 1.00),
    ("scrapingbee 50,000 pages", "scrapingbee", 50000, 0.38),
    ("render scrapingbee 100k", "scrapingbee", 100000, 0.99),
    ("render crawl4ai 100k", "crawl4ai_cloud", 100000, 0.825),
    ("worked example: firecrawl 60,000 basic", "firecrawl", 60000, 1.65),
    ("worked example: scrapingbee 60,000 basic", "scrapingbee", 60000, 0.32),
]:
    eq(label, per1000(name, pages, "render" if label.startswith("render") else "basic"), want, tol=0.006)
eq("worked example: firecrawl 60,000 json", per1000("firecrawl", 60000, "json"), 6.65, tol=0.006)
eq("worked example: annual delta", (c.block_cost(P["firecrawl"], 60000, "json")[1] - c.block_cost(P["firecrawl"], 60000, "basic")[1]) * 12, 3600, tol=0.01)
eq("worked example: 60,000 ratio", per1000("firecrawl", 60000, "basic") / per1000("scrapingbee", 60000, "basic"), 5.2, tol=0.06)

# --- plan names and the vendor's own words ---------------------------------------------
for name, plan in (("firecrawl", "Hobby"), ("firecrawl", "Standard"), ("firecrawl", "Growth"),
                   ("scrapingbee", "Hobby"), ("scrapingbee", "Freelance"),
                   ("crawl4ai_cloud", "Starter"), ("tavily", "Researcher (free)")):
    checks += 1
    if not any(p["name"] == plan for p in P[name]["plans_monthly"]):
        fails.append("plan %s/%s no longer exists in prices.json" % (name, plan))
for txt, label in [
    ("add 4 credits per page", "firecrawl quote"),
    ("2026-11-09/10", "read date"),
    ("labelled affiliate link", "affiliate label"),
    ("autonomous AI agent", "ai authorship"),
    ("Anti-bot success rate, latency, output quality", "not priced"),
    ("CC-BY-NC 4.0", "licence caveat"),
    ("2026-10-04", "ujeebu date"),
    ("python3 check.py", "reproduce line"),
    # prose multiples and differences, so a typo in a sentence fails like a typo in a table
    ("**5.2×**", "firecrawl cliff multiple"),
    ("**2.6×**", "scrapingbee cliff multiple"),
    ("+$80, **5.2×**", "firecrawl cliff sentence"),
    ("+$30, **2.6×**", "scrapingbee cliff sentence"),
    ("**1.00× — the multiplier is invisible**", "json invisible at 20,000"),
    ("**4.03×**", "json ratio"),
    ("$0.99 for a plain page and $3.99 for a JSON page", "the corrected claim"),
    ("$0.13", "jina low"),
    ("$0.63", "jina high"),
    ("5× spread", "jina spread in prose"),
    ("charge $0.99 to $1.50 whatever the page", "quoted competitor claim"),
    ("Hobby, $19 → **$3.80/1,000**", "firecrawl hobby rate"),
    ("Standard, $99 → **$19.80/1,000**", "firecrawl standard rate"),
    ("Hobby, $19 → **$0.25/1,000**", "scrapingbee hobby rate"),
    ("Freelance, $49 → **$0.65/1,000**", "scrapingbee freelance rate"),
    ("**$1.65 per 1,000**", "worked example firecrawl"),
    ("**$0.32 per 1,000**", "worked example scrapingbee"),
    ("**$6.65 per 1,000**", "worked example json"),
    ("**$3,600 a year**", "worked example annual delta"),
]:
    has(label, txt)

# --- no dollar figure in the README without a computation behind it --------------------
computed = set()
for kind in ("basic", "render", "json"):
    for pages in c.VOLUMES + [5000, 5001, 60000, 75000, 75001, 20001]:
        for n in c.KIND_PROVIDERS[kind]:
            v = per1000(n, pages, kind)
            if v is not None:
                computed.add(round(v, 2))
for n, p in P.items():
    if n == "jina_reader":
        continue
    for plan in p["plans_monthly"]:
        computed.add(round(float(plan["usd"]), 2))
for v in j.values():
    computed.add(round(v, 2))
for m in P["jina_reader"]["measured_tokens_per_page"]:
    computed.add(round(m["tokens"] * 0.05 / 1e6, 6))
computed |= {80.0, 30.0, 3600.0, 5.2, 2.6, 4.03, 1.00, 0.001}          # differences and ratios computed above
third_party = {0.99, 1.50, 0.05}                                # ujeebu's quote, jina's $/1M rate
checks += 1
for v in set(re.findall(r"\$(\d+(?:\.\d+)?)", README)):
    f = float(v)
    if any(abs(f - c_) <= 0.006 for c_ in computed) or any(abs(f - t) <= 0.006 for t in third_party):
        continue
    fails.append("README quotes $%s, which no computation in check.py produces" % v)

print("%d checks, %d fails" % (checks, len(fails)))
for f in fails:
    print("FAIL", f)
sys.exit(1 if fails else 0)
