#!/usr/bin/env python3
"""Short terminal anchors for A-v07, computed live from the experiment's report files (report/c1-blind.csv,
report/c1-attempts.csv, copied next to this script by render.sh). No number is typed here: every value is read or summed
from the CSVs. Cost parts use the lab gateway's prices (gateway/gateway.py: Sonnet 5.5 at US$ 2 / 10 per million tokens,
cache writes 1.25x, cache reads 0.05x), and the script checks that the parts add up to the cost the gateway booked.
Usage: show_results.py grid | tally | cost"""
import csv, sys
mode = sys.argv[1]
B = list(csv.DictReader(open("c1-blind.csv"))); A = list(csv.DictReader(open("c1-attempts.csv")))
G, R, Y, D, Z = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
setups = (("A", "one agent"), ("B", "team"))
res = lambda r: "failed" if r["validator"] != "resolved" else ("fix" if r["fix"] == "True" else "worse")
if mode == "grid":
    cell = {(r["case"], r["config"], int(r["rep"])): res(r) for r in B}
    col = {"fix": G, "worse": R, "failed": D}
    print(f"{'task':<6}{'one agent r1':>14}{'r2':>8}{'team r1':>12}{'r2':>8}")
    for t in sorted({r["case"] for r in B}):
        cs = [cell[(t, c, k)] for c in "AB" for k in (1, 2)]
        w = (14, 8, 12, 8)
        print(f"{t:<6}" + "".join(col[x] + f"{x:>{w[j]}}" + Z for j, x in enumerate(cs)))
elif mode == "tally":
    print(f"{'patches that passed my tests':<30}{'passed':>7}{'equiv':>7}{'valid':>7}{'worse':>7}{'fixes':>10}")
    tot = [0, 0, 0, 0]
    for c, name in setups:
        p = [r for r in B if r["config"] == c and r["validator"] == "resolved"]
        n = [len(p), sum(r["blind"] == "equivalente" for r in p), sum(r["blind"] == "valida" for r in p), sum(r["blind"] == "pior" for r in p)]
        tot = [a + b for a, b in zip(tot, n)]
        print(f"{name:<30}{n[0]:>7}{n[1]:>7}{n[2]:>7}{R}{n[3]:>7}{Z}{G}{n[1] + n[2]:>6} of {sum(r['config'] == c for r in B)}{Z}")
    print(f"{'all':<30}{tot[0]:>7}{tot[1]:>7}{tot[2]:>7}{R}{tot[3]:>7}{Z}")
elif mode == "cost":
    PI, PO, WX, RX = 2.0, 10.0, 1.25, 0.05
    S = lambda c, k: sum(float(a[k] or 0) for a in A if a["config"] == c)
    row = {}
    for c, name in setups:
        w, rd, o, pl = S(c, "cache_write") * WX * PI / 1e6, S(c, "cache_read") * RX * PI / 1e6, S(c, "out_tok") * PO / 1e6, S(c, "in_tok") * PI / 1e6
        assert abs(w + rd + o + pl - S(c, "usd")) < 0.01
        fixes = sum(r["fix"] == "True" for r in B if r["config"] == c)
        share = S(c, "cache_read") / (S(c, "in_tok") + S(c, "cache_write") + S(c, "cache_read"))
        row[c] = (S(c, "usd"), int(S(c, "model_calls")), share, w, o, rd, S(c, "usd") / fixes)
    print(f"{'':<14}{'spent':>8}{'calls':>7}{'from cache':>12}{'cache writes':>14}{'output':>8}{'cache reads':>13}{'per fix':>9}")
    for c, name in setups:
        u, n, sh, w, o, rd, pf = row[c]
        print(f"{name:<14}{'$%.2f' % u:>8}{n:>7}{'%.0f%%' % (sh * 100):>12}{'$%.2f' % w:>14}{'$%.2f' % o:>8}{'$%.2f' % rd:>13}{'$%.2f' % pf:>9}")
    d = [row["B"][k] - row["A"][k] for k in range(7)]
    print(f"{Y}{'team - agent':<14}{'%+.2f' % d[0]:>8}{'':>7}{'':>12}{'%+.2f' % d[3]:>14}{'%+.2f' % d[4]:>8}{'%+.2f' % d[5]:>13}{Z}")
