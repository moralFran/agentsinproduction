# Validator image: pristine task checkout + the maintainer's fix (used only as the positive control).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null && rm -rf /var/lib/apt/lists/* \
 && pip install -q --no-cache-dir pytest==9.2.0
COPY task/repo /task/repo
COPY task/fixed /task/fixed
COPY validator/validate.py /validator/validate.py
COPY validator/controls /validator/controls
RUN useradd -m -u 1000 v
USER v
