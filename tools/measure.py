#!/usr/bin/env python3
"""tools/measure.py — does Firecrawl's JSON mode (5 credits/page) pay for itself?

A reader of the companion article argued: request Markdown (1 credit) and do the JSON structuring
yourself with a small model. That is decidable, so this measures it instead of repeating it:

  input   = the Markdown Firecrawl returns for a page       (1 credit)
  output  = the JSON that page's fields produce, tokenised  (counted with tiktoken cl100k_base)
  price   = Novita's published list for deepseek-v4.1-flash (read 2026-11-08, see MODEL below)
  compare = the 4 extra credits per page, priced per Firecrawl plan (firecrawl.dev/pricing, 2026-11-10)

Two scenarios:
  A. catalogue: a 40-product listing page, Markdown rendered from the same records (self-contained)
  B. docs page: the real cleaned Markdown of firecrawl.dev/pricing, stored in tools/samples/

Writes docs/cost-model.json. tests/check_cost_model.py recomputes every figure printed in
docs/markdown-vs-json-cost.md from that JSON.

Nothing here claims a success rate, an extraction quality or a valid-JSON rate: it prices tokens,
and the vendor's own billing rule for error-status pages.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

import tiktoken

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENC = tiktoken.get_encoding("cl100k_base")


def tok(s):
    return len(ENC.encode(s))


# Firecrawl, https://www.firecrawl.dev/pricing — monthly price and monthly credit block.
PLANS = {
    "Free":     {"usd": 0,   "credits": 1000},
    "Hobby":    {"usd": 19,  "credits": 5000},
    "Standard": {"usd": 99,  "credits": 100000},
    "Growth":   {"usd": 399, "credits": 500000},
    "Scale":    {"usd": 749, "credits": 1000000},
}
CREDITS_PLAIN = 1
CREDITS_JSON = 5

MODEL = {
    "id": "deepseek/deepseek-v4.1-flash-1017",
    "source": "Novita published list, read 2026-11-08 (stage/costcalc dataset)",
    "usd_per_1m_input": 0.30,
    "usd_per_1m_output": 1.20,
    "usd_per_1m_cache_read": 0.006,
}

SCHEMA_CATALOGUE = (
    "Extract every product on this page as JSON. Reply with JSON only: an array of objects with the keys "
    "name (string), price (number, in the page's currency), currency (ISO code), in_stock (boolean), "
    "url (absolute URL or null). Do not invent fields. If a product lacks a price, use null and add "
    "\"price_note\": \"missing\". Preserve the page's order."
)
SCHEMA_DOCS = (
    "Extract the pricing plans on this page as JSON. Reply with JSON only: an object with keys "
    "vendor (string), as_of (date string as printed), currency (ISO code), plans (array of objects with "
    "name, credits (number), price_monthly_usd (number), price_annual_usd (number or null), notes (string)), "
    "credits_per_page (object: plain, json), failed_request_billing (string, one sentence quoting the page). "
    "Use null where the page does not say."
)

# A deliberately ordinary catalogue: 40 products, five fields each.
PRODUCTS = [
    {"name": "Part %02d" % i,
     "price": round(9.5 + i * 1.25, 2),
     "desc": "Replacement component %02d for the bench rig." % i}
    for i in range(1, 41)
]


def catalogue_markdown():
    out = ["# Catalog", "", "Forty products, priced.", ""]
    for p in PRODUCTS:
        out += ["## %s" % p["name"], "$%.2f" % p["price"], p["desc"], ""]
    return "\n".join(out)


def catalogue_output():
    recs = []
    for i, p in enumerate(PRODUCTS, 1):
        recs.append({"name": p["name"], "price": p["price"], "currency": "USD",
                     "in_stock": True, "url": "https://example.test/products/%d" % i})
    return json.dumps(recs, separators=(",", ":"))


def docs_markdown():
    with open(os.path.join(HERE, "samples", "firecrawl-pricing.md"),
              encoding="utf-8", errors="replace") as fh:
        return fh.read()


def docs_output():
    plans = [{"name": n, "credits": v["credits"], "price_monthly_usd": v["usd"],
              "price_annual_usd": None, "notes": "billed annually at a discount"}
             for n, v in PLANS.items()]
    obj = {"vendor": "Firecrawl", "as_of": "2026-09-04", "currency": "USD", "plans": plans,
           "credits_per_page": {"plain": 1, "json": 5},
           "failed_request_billing": (
               "A page that responds with an error status such as 403 or 404 is still returned to you "
               "and costs 1 credit; a scrape that returns no result is not charged.")}
    return json.dumps(obj, separators=(",", ":"))


def scenario(name, md, schema, out_json):
    t_schema, t_md, t_out = tok(schema), tok(md), tok(out_json)
    p_in, p_out = MODEL["usd_per_1m_input"], MODEL["usd_per_1m_output"]
    cost = (t_schema + t_md) * p_in / 1e6 + t_out * p_out / 1e6
    return {
        "name": name,
        "page_chars": len(md),
        "schema_tokens": t_schema,
        "page_tokens": t_md,
        "output_tokens": t_out,
        "input_tokens_total": t_schema + t_md,
        "local_structuring_usd_per_page": round(cost, 8),
        "md_sha256": hashlib.sha256(md.encode()).hexdigest(),
        "out_sha256": hashlib.sha256(out_json.encode()).hexdigest(),
    }


def main():
    sc = [scenario("catalogue_40_products", catalogue_markdown(), SCHEMA_CATALOGUE, catalogue_output()),
          scenario("docs_pricing_page", docs_markdown(), SCHEMA_DOCS, docs_output())]

    p_in, p_out = MODEL["usd_per_1m_input"], MODEL["usd_per_1m_output"]
    plans = {}
    for name, p in PLANS.items():
        credit_usd = p["usd"] / p["credits"]
        plans[name] = {
            "usd_per_credit": round(credit_usd, 8),
            "plain_page_usd": round(credit_usd * CREDITS_PLAIN, 8),
            "json_page_usd": round(credit_usd * CREDITS_JSON, 8),
            "json_premium_usd": round(credit_usd * (CREDITS_JSON - CREDITS_PLAIN), 8),
        }

    for s in sc:
        local = s["local_structuring_usd_per_page"]
        s["by_plan"], s["breakeven_output_tokens"] = {}, {}
        for name, row in plans.items():
            if row["json_page_usd"] == 0:
                s["by_plan"][name] = {"markdown_first_usd": round(local, 8), "json_mode_usd": 0.0,
                                      "markdown_first_is_cheaper": False}
                s["breakeven_output_tokens"][name] = None
                continue
            total = row["plain_page_usd"] + local
            s["by_plan"][name] = {
                "markdown_first_usd": round(total, 8),
                "json_mode_usd": row["json_page_usd"],
                "ratio_md_over_json": round(total / row["json_page_usd"], 4),
                "markdown_first_is_cheaper": total < row["json_page_usd"],
            }
            budget = row["json_premium_usd"] - s["input_tokens_total"] * p_in / 1e6
            s["breakeven_output_tokens"][name] = round(budget / p_out * 1e6) if budget > 0 else 0

    def cheapest_plan(credits_needed):
        ok = [(p["usd"], n) for n, p in PLANS.items() if p["credits"] >= credits_needed]
        return min(ok) if ok else (None, None)

    local = sc[0]["local_structuring_usd_per_page"]
    volumes = {}
    for pages in (20000, 60000, 100000):
        j_usd, j_plan = cheapest_plan(pages * CREDITS_JSON)
        p_usd, p_plan = cheapest_plan(pages * CREDITS_PLAIN)
        md_total = p_usd + pages * local
        volumes[str(pages)] = {
            "json_plan": j_plan, "json_plan_usd_monthly": j_usd,
            "plain_plan": p_plan, "plain_plan_usd_monthly": p_usd,
            "markdown_first_total_usd": round(md_total, 2),
            "json_is_cheaper": j_usd < md_total,
            "saving_markdown_first_usd": round(j_usd - md_total, 2),
            "saving_markdown_first_usd_per_year": round((j_usd - md_total) * 12, 2),
            "markdown_first_multiple": round(j_usd / md_total, 2),
            "same_block": j_plan == p_plan,
        }

    SUCCESS = 0.6047  # third-party benchmark sample quoted in README.md; not measured by me
    eff = {}
    for name, row in plans.items():
        if row["usd_per_credit"] == 0:
            continue
        eff[name] = {
            "plain_per_usable_page_usd": round(row["plain_page_usd"] / SUCCESS, 6),
            "json_per_usable_page_usd": round(row["json_page_usd"] / SUCCESS, 6),
            "multiple_over_plain_headline": round(1 / SUCCESS, 4),
        }

    out = {
        "measured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "tokeniser": "tiktoken cl100k_base",
        "firecrawl_plans_source": "https://www.firecrawl.dev/pricing (read 2026-11-10)",
        "firecrawl_billing_rule_quote": (
            "A scrape that returns no result is not charged. A page that responds with an error status "
            "such as 403 or 404 is still returned to you and costs 1 credit."),
        "firecrawl_format_rule_quote": (
            "On Scrape and Crawl, the JSON, Question, and Highlight formats add 4 credits per page"),
        "model": MODEL,
        "plans": plans,
        "scenarios": sc,
        "local_structuring_ref": "catalogue_40_products scenario",
        "volume_blocks": volumes,
        "success_rate_sample": {"value": SUCCESS,
                                "provenance": "third-party benchmark README quoted in README.md; not re-measured"},
        "effective_cost_per_usable_page": eff,
    }
    path = os.path.join(ROOT, "docs", "cost-model.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", path)
    for s in sc:
        print(s["name"], "in", s["input_tokens_total"], "out", s["output_tokens"],
              "local$", s["local_structuring_usd_per_page"],
              "breakeven(Standard)", s["breakeven_output_tokens"]["Standard"])
    for k, v in volumes.items():
        print(k, v["json_plan_usd_monthly"], "vs", v["markdown_first_total_usd"], v["markdown_first_multiple"])


if __name__ == "__main__":
    main()
