#!/usr/bin/env python3
"""What scraped pages cost per month, priced from each vendor's own plan ladder.

Model: pick the cheapest published plan whose monthly credit allowance COVERS the pages you
need, then divide that plan's price by the pages. That is what you actually pay when a
provider sells blocks rather than per-page units, and it is why the per-1,000 figure moves
with volume instead of staying at the headline rate.

  python3 cost.py                  # the table used in the README
  python3 cost.py --pages 50000 --kind json
  python3 cost.py --provider firecrawl --pages 8000 --kind json
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# kinds each provider actually prices on its own page. A provider is left out of a kind it
# does not publish a per-page multiplier for, rather than being shown as "no plan".
KIND_PROVIDERS = {
    "basic": ["firecrawl", "scrapingbee", "crawl4ai_cloud", "tavily", "jina_reader"],
    "render": ["scrapingbee", "crawl4ai_cloud"],
    "json": ["firecrawl"],
}
KIND_LABEL = {
    "basic": "plain page (Markdown/HTML)",
    "render": "JavaScript-rendered page",
    "json": "structured JSON output",
}
PROVIDERS = ["firecrawl", "scrapingbee", "crawl4ai_cloud", "tavily", "jina_reader"]
VOLUMES = [1000, 10000, 50000, 100000]


def load():
    with open(os.path.join(HERE, "prices.json")) as fh:
        return json.load(fh)


def cheapest_plan(plans, credits_needed):
    ok = [p for p in plans if p["credits"] >= credits_needed]
    if not ok:
        return None
    return min(ok, key=lambda p: (p["usd"], p["credits"]))


def block_cost(provider, pages, kind):
    """(plan_name, plan_usd, usd_per_1000) or None if no published plan covers it."""
    per_page = provider["credits_per_page"][kind]
    plan = cheapest_plan(provider["plans_monthly"], pages * per_page)
    if plan is None:
        return None
    return plan["name"], plan["usd"], plan["usd"] / pages * 1000.0


def jina_cost(data):
    """Jina bills output tokens, so its cost is a range set by the measured pages."""
    j = data["providers"]["jina_reader"]
    rate = j["usd_per_1m_tokens"]
    toks = sorted(m["tokens"] for m in j["measured_tokens_per_page"])
    out = {"low": toks[0], "median": toks[len(toks) // 2], "high": toks[-1]}
    return {k: v * rate / 1e6 * 1000.0 for k, v in out.items()}, out


def cells(data, kind, pages):
    row = {}
    for name in KIND_PROVIDERS[kind]:
        if name == "jina_reader":
            row[name] = round(jina_cost(data)[0]["median"], 2)
        else:
            r = block_cost(data["providers"][name], pages, kind)
            row[name] = None if r is None else round(r[2], 2)
    return row


def table(data):
    for kind in ("basic", "render", "json"):
        print("\n%s  ($ per 1,000 pages)" % KIND_LABEL[kind])
        print("%-12s" % "pages" + "".join("%16s" % p for p in KIND_PROVIDERS[kind]))
        for pages in VOLUMES:
            row = cells(data, kind, pages)
            print("%-12d" % pages + "".join(
                "%16s" % ("--" if row[p] is None else ("%.2f" % row[p])) for p in KIND_PROVIDERS[kind]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int)
    ap.add_argument("--kind", default="basic", choices=list(KIND_PROVIDERS))
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    data = load()

    if a.table or a.pages is None:
        table(data)
        print("\n-- = no published plan on that vendor's page covers the volume in that format.")
        print("jina is billed by output tokens; the figure is its median measured page (5,341 tokens).")
        return

    for name in ([a.provider] if a.provider else KIND_PROVIDERS[a.kind]):
        if name == "jina_reader":
            rng, toks = jina_cost(data)
            print("jina_reader      tokens/page %d/%d/%d  $%.2f-$%.2f per 1,000 (median %.2f)"
                  % (toks["low"], toks["median"], toks["high"], rng["low"], rng["high"], rng["median"]))
            continue
        p = data["providers"][name]
        r = block_cost(p, a.pages, a.kind)
        if r is None:
            print("%-16s no published plan covers %d %s pages" % (name, a.pages, a.kind))
        else:
            print("%-16s %-12s $%-8.2f $%.2f per 1,000 %s pages"
                  % (name, r[0], r[1], r[2], a.kind))


if __name__ == "__main__":
    main()
