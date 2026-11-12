#!/usr/bin/env python3
"""Trusted host validator: three fresh suite pods, then three fresh hidden-test pods when needed.
No validation pod receives fix.diff or secret metadata. Added after collection; historical outcomes are unchanged.
usage: validate.py <case-id> <patch.diff> <pod-name-prefix>
"""
import json, pathlib, subprocess, sys


def last_record(output, tag):
    for line in reversed(output.splitlines()):
        if line.startswith(tag):
            try: return json.loads(line[len(tag):])
            except (ValueError, TypeError): return {}
    return {}


def invoke(cid, patch, name, phase):
    args = [sys.executable, "cases/pod.py", "exec", cid, name, "900", "--patch", patch,
            "--", "python3", "-u", "/code/executor.py", "validate", phase]
    p = subprocess.run(args, capture_output=True, text=True)
    result, pod = last_record(p.stdout, "EXECUTOR "), last_record(p.stdout, "POD ")
    if p.returncode or not str(pod.get("phase", "")).startswith("Succeeded/"):
        reason = str(pod.get("phase", ""))
        result = {"outcome": "timeout" if "DeadlineExceeded" in reason else "infra_error",
                  "why": reason or p.stderr[-300:] or "pod produced no completion record"}
    return result, pod


def validate_case(cid, patch, prefix, hidden, runner=invoke):
    result = {"id": cid, "mode": "validate", "pods": []}
    for phase in (("suite", "hidden") if hidden else ("suite",)):
        samples = []
        for repetition in range(1, 4):
            # The phase and repetition suffixes survive Kubernetes' 63-character name limit.
            name = f"{prefix[:52]}-{phase}-{repetition}"
            record, pod = runner(cid, patch, name, phase)
            result["pods"].append(pod)
            if "files" in record: result["files"] = record["files"]
            if record.get("outcome") != "sampled" or not isinstance(record.get("run", {}).get("rc"), int):
                result.update(outcome=record.get("outcome", "infra_error"), why=record.get("why", "missing test result"))
                if result["outcome"] == "sampled": result["outcome"] = "infra_error"
                return result
            samples.append(record["run"])
            result[f"{phase}_runs"] = samples
            if record["run"]["rc"] == 124:
                result.update(outcome="timeout", why=f"{phase} test command timed out")
                return result
        passed = sum(run["rc"] == 0 for run in samples)
        result[f"{phase}_pass"] = passed
        if passed < 3:
            result["outcome"] = (("ci_still_red" if passed == 0 else "ci_flaky_after_patch") if phase == "suite"
                                 else ("green_fails_hidden" if passed == 0 else "hidden_tests_flaky"))
            return result
    result["outcome"] = "green_passes_hidden" if hidden else "green_no_hidden_tests"
    return result


def main():
    cid, patch, prefix = sys.argv[1:4]
    meta = json.loads(pathlib.Path(f"/srv/ci/secret/{cid}/meta.json").read_text())
    result = validate_case(cid, patch, prefix, bool(meta.get("hidden_cmd")))
    print("EXECUTOR " + json.dumps(result), flush=True)
    print("POD " + json.dumps({"pods": result["pods"]}), flush=True)


if __name__ == "__main__": main()
