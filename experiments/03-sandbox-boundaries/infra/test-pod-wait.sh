#!/usr/bin/env bash
# Offline test of pod_done (infra/pod-wait.sh) with a stand-in for kubectl: the wait must end when EITHER phase is
# reached, and at the timeout when neither is. No cluster. About 8 s.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/kubectl" <<'SH'
#!/usr/bin/env bash
# stand-in: `wait --for=jsonpath='{.status.phase}'=X pod/<name> --timeout=Ns` ends with 0 after 1 s if the pod's name
# says it reaches X ("ends-Succeeded", "ends-Failed"); otherwise it sits out its timeout and ends with 1.
phase="$(printf '%s\n' "$@" | sed -n "s/^--for=jsonpath=.*=\(.*\)$/\1/p")"
pod="$(printf '%s\n' "$@" | sed -n 's/^pod\///p')"; t="$(printf '%s\n' "$@" | sed -n 's/^--timeout=\(.*\)s$/\1/p')"
if [ "$pod" = "ends-$phase" ]; then sleep 1; exit 0; fi
sleep "$t"; exit 1
SH
chmod +x "$tmp/kubectl"; PATH="$tmp:$PATH"
. "$here/pod-wait.sh"
ok=0
t() { local name="$1" timeout="$2" lo="$3" hi="$4" s e d; s=$(python3 -c 'import time; print(time.time())')
      pod_done lab-x "$name" "$timeout"; e=$(python3 -c 'import time; print(time.time())')
      d=$(python3 -c 'import sys; d = float(sys.argv[2]) - float(sys.argv[1]); print(f"{d:.1f}", int(float(sys.argv[3]) <= d <= float(sys.argv[4])))' "$s" "$e" "$lo" "$hi")
      if [ "${d#* }" = 1 ]; then echo "PASS $5: returned after ${d% *} s"; else echo "FAIL $5: returned after ${d% *} s (expected $lo to $hi)"; ok=1; fi; }
t ends-Succeeded 30 0.8 3 "a pod that succeeds ends the wait"
t ends-Failed    30 0.8 3 "a pod that fails ends the wait too (it used to sit out the timeout)"
t never-ends      3 2.5 6 "neither phase: the wait ends at the timeout"
left=$(pgrep -f "$tmp/kubectl" | wc -l | tr -d ' ')
if [ "$left" = 0 ]; then echo "PASS no stand-in process left running"; else echo "FAIL $left stand-in processes left"; ok=1; fi
exit $ok
