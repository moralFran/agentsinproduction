#!/usr/bin/env python3
"""Integration probe (2026-11-12), runs INSIDE a probe pod. Prints what this container is and what it can reach.
Never prints content read from a file or from the network: only "readable"/"not readable", status codes and sizes.
Targets come from PROBE_TARGETS (JSON: node_ip, gw_pod_ip, other_pod_ip, dns_pod_ip, case_id)."""
import hashlib, json, os, socket, ssl, subprocess, urllib.request, urllib.error

T = json.loads(os.environ.get("PROBE_TARGETS", "{}")); TIMEOUT = 5
out = lambda kind, **kw: print("PROBE " + json.dumps({"kind": kind, **kw}), flush=True)

def tcp(host, port):
    s = socket.socket(); s.settimeout(TIMEOUT)
    try: s.connect((host, int(port))); return "open"
    except socket.timeout: return "timeout"
    except OSError as e: return f"error: {e.strerror or e}"
    finally: s.close()

def http(url, headers=None, data=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}, data=data), timeout=TIMEOUT)
        body = r.read(); return f"http {r.status}", len(body), hashlib.sha256(body).hexdigest()[:16]
    except urllib.error.HTTPError as e: return f"http {e.code}", None, None
    except Exception as e:
        reason = getattr(e, "reason", e)
        return ("timeout" if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason) else f"error: {reason}"), None, None

def identity():
    st = {l.split(":")[0]: l.split(":", 1)[1].strip() for l in open("/proc/self/status") if l.split(":")[0] in ("Seccomp", "Seccomp_filters", "NoNewPrivs", "CapEff", "CapBnd", "Uid", "Gid")}
    out("identity", uid=os.getuid(), gid=os.getgid(), kernel=os.uname().release, status=st)
    mounts = []
    for l in open("/proc/self/mountinfo"):
        f = l.split(); mp = f[4]
        if mp.startswith(("/srv", "/in", "/input", "/code", "/tmp", "/validation", "/probe", "/admin", "/secrets")):
            mounts.append({"path": mp, "opts": f[5].split(",")[0]})
    out("mounts", mounts=sorted(mounts, key=lambda m: m["path"]))
    cid = T.get("case_id", os.environ.get("CASE_ID", ""))
    for p in ("/in", "/in/patch.diff", "/in/hidden.diff", "/in/fix.diff", "/srv/ci/secret", f"/srv/ci/secret/{cid}", f"/srv/ci/secret/{cid}/meta.json",
              f"/srv/ci/secret/{cid}/fix.diff", f"/srv/ci/secret/{cid}/hidden.diff", "/srv/ci/admin-key", "/validation/prepared.json",
              f"/srv/ci/cases/{cid}/meta.json", f"/srv/ci/cases/{cid}/snapshot", f"/srv/ci/cases/{cid}/repo", "/var/run/secrets/kubernetes.io/serviceaccount/token"):
        try:
            if os.path.isdir(p): os.listdir(p); state = "readable (directory)"
            else:
                with open(p, "rb") as f: f.read(1)
                state = "readable"
        except OSError as e: state = f"not readable ({e.strerror})"
        out("path", path=p, state=state)
    for p in (f"/srv/ci/cases/{cid}/snapshot/.probe-write", f"/srv/ci/cases/{cid}/repo/.probe-write", "/validation/.probe-write", "/input/.probe-write", f"/srv/ci/cases/{cid}/.probe-write"):
        if not os.path.isdir(os.path.dirname(p)): continue
        try:
            open(p, "w").close(); os.unlink(p); state = "writable"
        except OSError as e: state = f"not writable ({e.strerror})"
        out("write", path=os.path.dirname(p), state=state)
    if os.path.isdir(f"/srv/ci/cases/{cid}/repo/.git"):
        g = subprocess.run(["git", "status", "--porcelain"], cwd=f"/srv/ci/cases/{cid}/repo", capture_output=True, text=True)
        out("worktree", git_status_lines=len(g.stdout.splitlines()), rc=g.returncode)
    if os.path.exists("/validation/prepared.json"):
        r = json.load(open("/validation/prepared.json")); out("prepared_record", outcome=r.get("outcome"), phase=r.get("phase"), files=r.get("files"))

def network():
    try: out("dns", name="proxy.golang.org", result="resolved", n=len(socket.getaddrinfo("proxy.golang.org", 443)))
    except OSError as e: out("dns", name="proxy.golang.org", result=f"error: {e}")
    # public HTTPS: a real dependency download (Go module zip and the PyPI index page); by name and, for pods without DNS, by address
    for url in ("https://proxy.golang.org/github.com/gobwas/pool/@v/v0.2.1.zip", "https://pypi.org/simple/pytest/", "http://example.com/"):
        r, n, h = http(url); out("public_http", url=url, result=r, bytes=n, sha256_16=h)
    for host, port, label in (("1.1.1.1", 443, "public address, port 443"), ("1.1.1.1", 53, "public address, port 53 (not 80/443)"),
                              ("169.254.169.254", 80, "cloud metadata endpoint"),
                              (T.get("node_ip"), 22, "node private address, ssh"), (T.get("node_ip"), 6443, "node private address, Kubernetes API"),
                              (T.get("node_ip"), 10250, "node private address, kubelet"), ("10.43.0.1", 443, "Kubernetes API ClusterIP"),
                              ("10.43.210.10", 8080, "gateway ClusterIP, model port"), ("10.43.210.10", 8081, "gateway ClusterIP, admin port"),
                              (T.get("gw_pod_ip"), 8080, "gateway pod address, model port"), (T.get("gw_pod_ip"), 8081, "gateway pod address, admin port"),
                              (T.get("other_pod_ip"), T.get("other_pod_port", 10250), "another pod (metrics-server)"), (T.get("dns_pod_ip"), 53, "DNS pod, tcp 53")):
        if host: out("tcp", target=label, addr=f"{host}:{port}", result=tcp(host, port))
    r, n, _ = http("http://169.254.169.254/computeMetadata/v1/instance/id", {"Metadata-Flavor": "Google"}); out("metadata_http", result=r, bytes=n)
    r, n, _ = http("http://10.43.210.10:8080/healthz"); out("gateway_healthz", result=r, bytes=n)
    r, n, _ = http("http://10.43.210.10:8081/state"); out("gateway_admin_state_no_token", result=r, bytes=n)
    r, n, _ = http("http://10.43.210.10:8080/v1/messages", {"content-type": "application/json", "x-run-id": "probe-unknown-run"},
                   json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 1, "messages": [{"role": "user", "content": "x"}]}).encode())
    out("gateway_model_unknown_run", result=r, note="403 = reached the gateway, which refused the unknown run id; no provider call")

if __name__ == "__main__":
    out("start", role=os.environ.get("PROBE_ROLE", ""))
    identity(); network()
    out("end")
