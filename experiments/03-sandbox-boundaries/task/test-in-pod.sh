#!/usr/bin/env bash
# Runs ON aip-kata-01. Runs the task's target tests inside a pod made from the agent's own image and spec, on a copy
# of the frozen checkout, the way the agent starts (/task/repo copied to /work/repo).   usage: test-in-pod.sh <pod>
set -uo pipefail
export KUBECONFIG=~/.kube/config
kubectl -n lab-agent exec "${1:?pod}" -- sh -c 'rm -rf /work/repo && cp -r /task/repo /work/repo && cd /work/repo && COLUMNS=74 python -m pytest -q --tb=no -p no:cacheprovider tests/test_fileutils.py'
