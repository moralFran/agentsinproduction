#!/usr/bin/env python3
import collections, json, sys
c = collections.defaultdict(collections.Counter)
for l in open(sys.argv[1]):
    r = json.loads(l); c[(r["identity"], r["probe"])][(r["result"], "secret returned" if r["secret_in_body"] else "no secret")] += 1
for k in sorted(c): print(f"{k[0]:9} {k[1]:18} " + ", ".join(f"{v}× {n[0]} ({n[1]})" for n, v in c[k].most_common()))
