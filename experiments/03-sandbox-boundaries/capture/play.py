#!/usr/bin/env python3
"""Plays one terminal capture on the machine where the commands must run: prints the prompt, "types" each command,
then RUNS it for real (bash -c) with its live output. Only the typing is simulated; nothing on screen is written by
hand. Recorded from the Mac with asciinema by capture/record.sh.   usage: play.py <capture-name>"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
spec = json.load(open(os.path.join(HERE, "captures.json")))["captures"][sys.argv[1]]
env = dict(os.environ, KUBECONFIG=os.path.expanduser("~/.kube/config"), LC_ALL="C.UTF-8", TERM="xterm-256color")
PROMPT = "\033[38;2;74;222;128m❯\033[0m "
def out(s): sys.stdout.write(s); sys.stdout.flush()
time.sleep(0.5)
for step in spec["steps"]:
    out(PROMPT); time.sleep(step.get("before", 0.35))
    for ch in step["cmd"]: out(ch); time.sleep(0.004)
    time.sleep(0.3); out("\n")
    subprocess.run(["bash", "-c", step["cmd"] + " 2>&1"], cwd=os.path.dirname(HERE), env=env, stdin=subprocess.DEVNULL)
    time.sleep(step.get("after", 1.2))
out(PROMPT); time.sleep(spec.get("hold", 2.0)); out("\n")
