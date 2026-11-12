# Validator image: pristine task checkout + the maintainer's fix (the reference of each evaluation). In the pod the
# image's copy of the fix is hidden under a mount and the validator deletes the copy it works from before any patch
# code runs (k8s/71-validator-pod.yaml, validate.py). The negative controls are NOT in the image: one of them
# contains the fix; the runner passes each patch in through a ConfigMap.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null && rm -rf /var/lib/apt/lists/* \
 && pip install -q --no-cache-dir pytest==9.2.0
COPY task/repo /task/repo
COPY task/fixed /task/fixed
COPY validator/validate.py /validator/validate.py
RUN useradd -m -u 1000 v
USER 1000
