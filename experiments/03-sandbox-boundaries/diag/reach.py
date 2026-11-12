"""Runs INSIDE the agent's own image and pod spec (passed to python3 -c by diag/reach.sh). What the final
configuration can reach. The endpoint's address comes from lab.env through the environment; there is no default."""
import json, os, sys, urllib.request
if not os.environ.get("ENDPOINT_IP"): sys.exit("ENDPOINT_IP is not set: run this through diag/reach.sh, which reads lab.env")
def t(name, url, data=None, headers={}):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=4); print(name, "->", "http", r.status)
    except urllib.error.HTTPError as e: print(name, "->", "http", e.code)
    except Exception as e: print(name, "->", type(e).__name__, str(getattr(e, "reason", e))[:60])
t("outside endpoint", "http://" + os.environ["ENDPOINT_IP"] + ":8080/probe/final-agent-image")
t("internal api", "http://10.43.200.20:8080/customers")
t("gcp metadata", "http://169.254.169.254/computeMetadata/v1/instance/hostname", headers={"Metadata-Flavor": "Google"})
t("kubernetes api", "https://10.43.0.1:443/version")
t("gateway other path", "http://10.43.200.10:8080/v1/models")
t("gateway model call", "http://10.43.200.10:8080/v1/messages", data=json.dumps({"model": "claude-haiku-5-5", "max_tokens": 8, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]}).encode(), headers={"content-type": "application/json", "anthropic-version": "2023-06-01", "x-run-id": "inspect"})
