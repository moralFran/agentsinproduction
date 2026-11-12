#!/usr/bin/env python3
"""Integration (2026-11-12). Builds network-controls.md from the probe logs (network/*.log, network/timing, network/steady).
usage: build-network-summary.py <integration-dir>"""
import glob, json, os, re, subprocess, sys
d = sys.argv[1]
def records(path, tag):
    out = []
    for line in open(path):
        i = line.find(tag + " {")
        if i >= 0: out.append(json.loads(line[i + len(tag) + 1:]))
    return out
kinds = [("ctl", "control: namespace `default`, no policy"), ("prep", "`ci-prep` (preparation)"), ("agent", "`ci-agent` (agent)"),
         ("exec-repro", "`ci-exec` (repro, no init container)"), ("exec-fixed", "`ci-exec` (repro fixed)"), ("exec-fixed-agent-cache", "`ci-exec` (repro fixed-agent-cache)"),
         ("exec-validate-suite", "`ci-exec` validation, test container (suite)"), ("exec-validate-hidden", "`ci-exec` validation, test container (hidden)")]
data = {k: records(os.path.join(d, "network", f"probe-{k}.log"), "PROBE") for k, _ in kinds if os.path.exists(os.path.join(d, "network", f"probe-{k}.log"))}
short = lambda r: {"open": "open"}.get(r, "refused" if "refused" in r else ("timeout" if "timeout" in r or "timed out" in r else ("no DNS" if "name resolution" in r else r)))
L = ["# Network and pod controls on the cluster, follow-up round (2026-11-12)", "",
     "Every pod below was built with the harness's own spec builder (`cases/pod.py build_spec`, `cases/prep.py worker_spec`); only the command",
     "of the main container was replaced by the probe (`controls/netprobe.py`), and CPU/memory *requests* were lowered. Raw logs: `network/`.",
     "The probe prints status codes and sizes only. The control pod (namespace `default`, Kata, no NetworkPolicy) is the positive control:",
     "what is reachable when no policy applies.", "",
     "## 1. One full probe per pod kind (first seconds of the pod included)", ""]
rows = []
for k, _ in kinds:
    for r in data.get(k, []):
        key = {"dns": "DNS lookup of proxy.golang.org", "metadata_http": "HTTP GET to the metadata endpoint", "gateway_healthz": "HTTP GET gateway /healthz (model port)",
               "gateway_admin_state_no_token": "HTTP GET gateway admin /state, no token", "gateway_model_unknown_run": "POST /v1/messages with an unknown run id"}.get(r["kind"])
        if r["kind"] == "public_http": key = "download " + r["url"]
        if r["kind"] == "tcp": key = f"TCP {r['target']} ({r['addr']})"
        if key and key not in rows: rows.append(key)
def cell(k, key):
    for r in data.get(k, []):
        if r["kind"] == "public_http" and key == "download " + r["url"]: return short(r["result"]) + (f" ({r['bytes']} B)" if r.get("bytes") else "")
        if r["kind"] == "tcp" and key == f"TCP {r['target']} ({r['addr']})": return short(r["result"])
        if r["kind"] == "dns" and key.startswith("DNS"): return "resolved" if r["result"] == "resolved" else "no DNS"
        if r["kind"] == "metadata_http" and key.startswith("HTTP GET to the metadata"): return short(r["result"])
        if r["kind"] == "gateway_healthz" and "healthz" in key: return short(r["result"])
        if r["kind"] == "gateway_admin_state_no_token" and "admin /state" in key: return short(r["result"])
        if r["kind"] == "gateway_model_unknown_run" and key.startswith("POST"): return short(r["result"])
    return "-"
present = [(k, label) for k, label in kinds if k in data]
L += ["| Target | " + " | ".join(label for _, label in present) + " |", "|---|" + "---|" * len(present)]
L += [f"| {key} | " + " | ".join(cell(k, key) for k, _ in present) + " |" for key in rows]
L += ["", "Read with section 2: the probe starts with DNS and the downloads, so the pods whose first lines say `http 200` and later lines say",
      "`refused` (`ci-agent`, `ci-exec` repro) were inside the start-up window described below; `ci-exec` (repro fixed) ran its whole probe inside it.", "",
      "### What each container is and can read", "", "| Pod | uid:gid | Guest kernel | Seccomp | NoNewPrivs | CapEff | Mounts (ro/rw) | Readable | Not present |", "|---|---|---|---|---|---|---|---|---|"]
for k, label in present:
    ident = next((r for r in data[k] if r["kind"] == "identity"), {}); st = ident.get("status", {})
    mounts = next((r["mounts"] for r in data[k] if r["kind"] == "mounts"), [])
    cid = "gobwas-ws-a567dfd6"; tidy = lambda p: p.replace(f"/srv/ci/cases/{cid}", "<case>").replace(f"/srv/ci/secret/{cid}", "<secret>")
    readable = [tidy(r["path"]) for r in data[k] if r["kind"] == "path" and r["state"].startswith("readable")]
    absent = [tidy(r["path"]) for r in data[k] if r["kind"] == "path" and not r["state"].startswith("readable") and r["path"] in ("/in/patch.diff", "/in/hidden.diff", "/in/fix.diff", f"/srv/ci/secret/{cid}/meta.json", "/srv/ci/admin-key")]
    L.append(f"| {label} | {ident.get('uid')}:{ident.get('gid')} | {ident.get('kernel')} | {st.get('Seccomp')} | {st.get('NoNewPrivs')} | {st.get('CapEff')} | "
             + ", ".join(f"{tidy(m['path'])} {m['opts']}" for m in mounts if m["path"] != "/probe") + " | " + ", ".join(readable) + " | " + ", ".join(absent) + " |")
L += ["", "`<case>` = `/srv/ci/cases/gobwas-ws-a567dfd6`, `<secret>` = `/srv/ci/secret/gobwas-ws-a567dfd6`. Host kernel 7.0.0-1017-gcp; a guest kernel of 6.18.56 shows the Kata VM.",
      "`Seccomp: 0` inside the guest in every pod although the pod spec asks for `RuntimeDefault` (same as experiment 03).", ""]
t = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "summarize-timing.py"), os.path.join(d, "network", "timing")], capture_output=True, text=True).stdout
L += ["## 2. When the policy starts to apply to a new pod (`controls/nettime.py`)", "",
      "`-fu*`: 12 s probes at the end of the follow-up round, with nothing else running. The first round has the larger sample (`../integration-2026-11-12/network-controls.md`).", "", t]
# aggregate: start-up window per pod kind, and single connections that should never happen
import collections
START = ("public", "metadata", "node", "kubernetes"); agg = collections.OrderedDict(); odd = []
for f in sorted(glob.glob(os.path.join(d, "network", "timing", "probe-*.log"))):
    name = os.path.basename(f)[6:-4]; kind = re.sub(r"-(t1|busy\d+|idle\d+|fu\d+)$", "", name); cond = "idle" if ("idle" in name or "-fu" in name) else "busy"
    s = next((r for r in records(f, "NETTIME") if r.get("event") == "summary"), None)
    if not s: continue
    t = s["targets"]; blocked_targets = [k for k in t if k.startswith(START) and not (kind == "prep" and k.startswith("public"))]
    last = [t[k]["last_open_s"] for k in blocked_targets if t[k]["open"] and t[k]["last_open_s"] <= 1.5]   # later ones are listed below
    a = agg.setdefault((kind, cond), {"pods": 0, "window": 0, "last": []}); a["pods"] += 1
    if last: a["window"] += 1; a["last"].append(max(last))
    for k, v in t.items():
        expected_open = (kind == "agent" and k.startswith("gateway model")) or (kind == "prep" and k.startswith(("public", "dns")))
        if k.startswith("gateway") and v["open"] and not expected_open: odd.append(f"`{name}`: {k} reachable {v['open']} time(s), last at {v['last_open_s']} s")
        elif not expected_open and v["open"] and v["last_open_s"] > 1.5: odd.append(f"`{name}`: {k} still reachable at {v['last_open_s']} s")
        if kind == "agent" and k.startswith("gateway model") and v["blocked"]: odd.append(f"`{name}`: agent refused on the gateway model port {v['blocked']} time(s), first at {v['first_blocked_s']} s (expected reachable)")
L += ["", "### Start-up window, per pod kind", "",
      "A pod counts as \"had a window\" when the public address, the metadata endpoint, the node or the Kubernetes API ClusterIP (for `ci-prep`: the last three)",
      "answered at least once although the namespace's policy forbids it. The probe samples every ~0.3 s, so \"last reachable 0.65 s\" means blocked by ~1.0 s.", "",
      "| Pod kind | Condition | Pods | Had a window | Last reachable, min to max (s) |", "|---|---|---|---|---|"]
L += [f"| {k} | {c} | {a['pods']} | {a['window']} | {(str(min(a['last'])) + ' to ' + str(max(a['last']))) if a['last'] else '-'} |" for (k, c), a in agg.items()]
L += ["", "### Other single observations in the timing probes", ""] + [f"- {x}" for x in odd] + [""]
L += ["## 3. Five minutes of steady state while other pods were created and deleted (`controls/netflap.py`)", "",
      "One connection attempt per target every ~0.2 s (0.5 s timeout). \"after 5 s\" excludes the start-up window.", "",
      "| Pod | Target | Tries | Reachable | Reachable after 5 s | Blocked after 5 s |", "|---|---|---|---|---|---|"]
for f in sorted(glob.glob(os.path.join(d, "network", "steady", "probe-*.log"))):
    s = next((r for r in records(f, "NETFLAP") if r.get("event") == "summary"), None)
    if not s: continue
    for target, v in s["targets"].items():
        L.append(f"| {os.path.basename(f)[6:-4]} | {target} | {v['tries']} | {v['open']} | {v['open_after_5s']} | {v['blocked_after_5s']} |")
open(os.path.join(d, "network-controls.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
