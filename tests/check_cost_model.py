#!/usr/bin/env python3
"""tests/check_cost_model.py — every figure in docs/markdown-vs-json-cost.md, recomputed.

Three independent layers, so a wrong number cannot hide in one of them:
  1. re-tokenise the inputs and rebuild the measurements in memory (tools/measure.py functions),
     then compare the hashes and token counts with docs/cost-model.json;
  2. recompute money from those token counts and the model price, and the plan arithmetic from the
     vendor's monthly price and credit block — never from a number already stored in the JSON;
  3. assert that every printed figure appears in the Markdown with the right wording.

Exit 0 = all checks pass. Any failure prints the line and exits 1.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import measure  # noqa: E402

fails = 0
checks = 0


def ok(cond, label):
    global fails, checks
    checks += 1
    if not cond:
        fails += 1
        print("FAIL:", label)


def norm(text):
    """Markdown-insensitive compare: drop emphasis, blockquote marks, collapse whitespace."""
    text = text.replace("**", "").replace("\n> ", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def main():
    raw = open(os.path.join(ROOT, "docs", "markdown-vs-json-cost.md"), encoding="utf-8").read()
    doc = norm(raw)
    stored = json.load(open(os.path.join(ROOT, "docs", "cost-model.json")))

    # ---------- layer 1: rebuild the measurements from the inputs
    rebuilt = [measure.scenario("catalogue_40_products", measure.catalogue_markdown(),
                                measure.SCHEMA_CATALOGUE, measure.catalogue_output()),
               measure.scenario("docs_pricing_page", measure.docs_markdown(),
                                measure.SCHEMA_DOCS, measure.docs_output())]
    for a, b in zip(rebuilt, stored["scenarios"]):
        ok(a["name"] == b["name"], "scenario name")
        ok(a["md_sha256"] == b["md_sha256"], a["name"] + ": markdown hash")
        ok(a["out_sha256"] == b["out_sha256"], a["name"] + ": output hash")
        ok(a["schema_tokens"] == b["schema_tokens"], a["name"] + ": schema tokens")
        ok(a["page_tokens"] == b["page_tokens"], a["name"] + ": page tokens")
        ok(a["output_tokens"] == b["output_tokens"], a["name"] + ": output tokens")
        ok(a["page_chars"] == b["page_chars"], a["name"] + ": page chars")
        ok(abs(a["local_structuring_usd_per_page"] - b["local_structuring_usd_per_page"]) < 1e-9,
           a["name"] + ": local cost")

    p_in = measure.MODEL["usd_per_1m_input"]
    p_out = measure.MODEL["usd_per_1m_output"]
    cat, docs = stored["scenarios"]
    for s in (cat, docs):
        recomputed = (s["schema_tokens"] + s["page_tokens"]) * p_in / 1e6 + s["output_tokens"] * p_out / 1e6
        ok(abs(recomputed - s["local_structuring_usd_per_page"]) < 1e-9, s["name"] + ": money from tokens")

    # ---------- layer 2: plan arithmetic from the vendor's price and block
    for name, p in measure.PLANS.items():
        credit = p["usd"] / p["credits"]
        row = stored["plans"][name]
        ok(abs(row["usd_per_credit"] - credit) < 1e-9, name + ": $/credit")
        ok(abs(row["json_page_usd"] - credit * 5) < 1e-9, name + ": JSON page price")
        ok(abs(row["plain_page_usd"] - credit * 1) < 1e-9, name + ": plain page price")
        ok(abs(row["json_premium_usd"] - credit * 4) < 1e-9, name + ": 4-credit premium")

        md_total = credit + cat["local_structuring_usd_per_page"]
        ok(abs(cat["by_plan"][name]["markdown_first_usd"] - md_total) < 1e-9, name + ": markdown-first total")
        if credit == 0:
            ok(stored["scenarios"][0]["breakeven_output_tokens"][name] is None, name + ": break-even n/a on free")
            ok(stored["scenarios"][1]["breakeven_output_tokens"][name] is None, name + ": break-even n/a on free")
            continue
        be = (credit * 4 - cat["input_tokens_total"] * p_in / 1e6) / p_out * 1e6
        ok(abs(stored["scenarios"][0]["breakeven_output_tokens"][name] - round(be)) <= 1,
           name + ": catalogue break-even")
        be2 = (credit * 4 - docs["input_tokens_total"] * p_in / 1e6) / p_out * 1e6
        ok(abs(stored["scenarios"][1]["breakeven_output_tokens"][name] - round(be2)) <= 1,
           name + ": docs break-even")

    # ---------- volumes: cheapest plan must cover the credits, and the totals must add up
    for vol, row in stored["volume_blocks"].items():
        pages = int(vol)
        json_cr, plain_cr = pages * 5, pages * 1
        j = min((p["usd"], n) for n, p in measure.PLANS.items() if p["credits"] >= json_cr)
        pl = min((p["usd"], n) for n, p in measure.PLANS.items() if p["credits"] >= plain_cr)
        ok((row["json_plan_usd_monthly"], row["json_plan"]) == j, vol + ": JSON plan")
        ok((row["plain_plan_usd_monthly"], row["plain_plan"]) == pl, vol + ": plain plan")
        total = pl[0] + pages * cat["local_structuring_usd_per_page"]
        ok(abs(row["markdown_first_total_usd"] - round(total, 2)) < 0.01, vol + ": markdown-first total")
        ok(row["json_is_cheaper"] == (j[0] < total), vol + ": which is cheaper")
        ok(abs(row["saving_markdown_first_usd"] - round(j[0] - total, 2)) < 0.01, vol + ": saving")

    # ---------- the 403 arithmetic
    s = stored["success_rate_sample"]["value"]
    for name, row in stored["effective_cost_per_usable_page"].items():
        credit = measure.PLANS[name]["usd"] / measure.PLANS[name]["credits"]
        ok(abs(row["plain_per_usable_page_usd"] - round(credit / s, 6)) < 1e-9, name + ": usable plain")
        ok(abs(row["json_per_usable_page_usd"] - round(credit * 5 / s, 6)) < 1e-9, name + ": usable JSON")

    # ---------- layer 3: the numbers as printed
    ok(cat["input_tokens_total"] == 850, "doc: catalogue input tokens")
    ok(cat["page_chars"] == 2555, "doc: catalogue chars")
    for frag in ["850 (81 + 769)", "1,243", "$0.00175",
                 "6,022 (101 + 5,921)", "249", "$0.00211",
                 "2,555 chars", "23,397 chars"]:
        ok(norm(frag) in doc, "doc fragment: " + frag)

    rows = {
        "Hobby": ("$0.0038", "$0.01900", "$0.00555", "29.2%"),
        "Standard": ("$0.00099", "$0.00495", "$0.00274", "55.3%"),
        "Growth": ("$0.000798", "$0.00399", "$0.00254", "63.8%"),
        "Scale": ("$0.000749", "$0.00375", "$0.00250", "66.6%"),
    }
    for name in rows:
        r = stored["plans"][name]
        share = cat["by_plan"][name]["markdown_first_usd"] / r["json_page_usd"] * 100
        ok("%.1f%%" % share == rows[name][3], name + ": computed share")
        ok("$%.5f" % r["json_page_usd"] == rows[name][1], name + ": computed JSON price")
        ok("$%.5f" % cat["by_plan"][name]["markdown_first_usd"] == rows[name][2], name + ": computed md price")
        line = "| %s | %s |" % (name, " | ".join(rows[name]))
        ok(line in doc, "doc plan row: " + name)

    for plan, printed_cat, printed_docs in [("Hobby", "12,454", "11,161"),
                                            ("Standard", "3,088", "1,794"),
                                            ("Growth", "2,448", "1,154"),
                                            ("Scale", "2,284", "991")]:
        ok("{:,}".format(cat["breakeven_output_tokens"][plan]) == printed_cat, plan + ": break-even printed")
        ok(printed_cat in doc, plan + ": break-even appears in the doc")
        ok("{:,}".format(docs["breakeven_output_tokens"][plan]) == printed_docs,
           plan + ": break-even printed (docs)")
        ok(printed_docs in doc, plan + ": docs break-even appears in the doc")

    v = stored["volume_blocks"]
    ok("$99 (100,000 credits) | Standard $99 + $34.93 = $133.93" in doc, "doc: 20,000 row")
    ok("$399 (500,000 credits) | Standard $99 + $104.80 = $203.80" in doc, "doc: 60,000 row")
    ok("$399 (500,000 credits) | Standard $99 + $174.66 = $273.66" in doc, "doc: 100,000 row")
    ok("$195.20/month" in doc and "$2,342" in doc, "doc: 60,000 monthly and annual saving")
    ok("%.2f×" % v["60000"]["markdown_first_multiple"] == "1.96×" and
       doc.count("1.96×") == 2, "doc: 60,000 multiple (title and table)")
    ok("%.2f×" % v["100000"]["markdown_first_multiple"] == "1.46×" and
       "markdown-first, 1.46×" in doc, "doc: 100,000 multiple")
    ok(v["60000"]["same_block"] is False and v["20000"]["same_block"] is True, "volumes: block change")
    ok(abs(v["60000"]["markdown_first_total_usd"] - 203.80) < 0.01, "volume 60k total")
    ok(abs(v["60000"]["saving_markdown_first_usd"] - 195.20) < 0.01, "volume 60k saving")
    ok(round(v["60000"]["saving_markdown_first_usd"] * 12, 0) == 2342, "volume 60k annual saving")

    eff = stored["effective_cost_per_usable_page"]["Standard"]
    ok("$0.001637" in doc and "$0.008186" in doc, "doc: effective cost per usable page")
    ok("1.65×" in doc, "doc: 1.65 multiple")
    ok(abs(eff["plain_per_usable_page_usd"] - 0.001637) < 1e-6, "usable plain at Standard")

    ratio = stored["plans"]["Standard"]["json_page_usd"] / cat["local_structuring_usd_per_page"]
    ok("%.2f×" % ratio == "2.83×", "computed re-extraction multiple")
    ok("2.83×" in doc, "doc: 2.83 appears")

    ok(norm(stored["firecrawl_billing_rule_quote"]) in doc, "doc: billing rule quote verbatim")
    ok("add 4 credits per page" in doc, "doc: format rule quote")

    for bad in ["affiliate", "promo code", "% off"]:
        ok(bad not in raw, "doc: must not contain " + bad)
    urls = re.findall(r"https?://[^\s)\"]+", raw)
    ok(urls == ["https://a9n9.net"], "doc: only the disclosure URL")

    print("%d checks, %d failed" % (checks, fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
