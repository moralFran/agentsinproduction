# Agent image: Python, git, pytest, the SDK and the frozen task checkout. No credentials, no maintainer fix.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null && rm -rf /var/lib/apt/lists/* \
 && pip install -q --no-cache-dir anthropic==2.8.0 pytest==9.2.0
COPY task/repo /task/repo
COPY agent/agent.py agent/selfcheck.py /agent/
RUN useradd -m -u 1000 agent && mkdir /work && chown agent /work
USER 1000
WORKDIR /work
CMD ["python3", "-u", "/agent/agent.py"]
