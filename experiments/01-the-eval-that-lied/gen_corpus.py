#!/usr/bin/env python3
"""Generate the fictional product docs (corpus/) and the eval set (questions.jsonl).

Everything is derived from one FACTS table so the docs and the expected answers can never disagree.
Product: "Relayline", a fictional webhook relay service. All numbers are invented.
"""
import json, os, pathlib

ROOT = pathlib.Path(__file__).parent
CORPUS = ROOT / "corpus"
CORPUS.mkdir(exist_ok=True)

FACTS = {
    # pricing
    "free_events": "10,000", "starter_price": "$29", "starter_events": "250,000",
    "growth_price": "$149", "growth_events": "2,000,000", "overage_per_1k": "$0.40",
    "annual_discount": "17%", "currency": "USD",
    # limits
    "payload_max": "256 KB", "free_retention_days": "3", "paid_retention_days": "30",
    "max_retries": "8", "retry_backoff_base": "5 seconds", "retry_backoff_cap": "2 hours",
    "endpoints_free": "2", "endpoints_starter": "25", "endpoints_growth": "unlimited",
    "rate_limit_rps": "500", "burst_rps": "2,000", "timeout_seconds": "15",
    # regions
    "regions": "us-east, eu-west, ap-south", "default_region": "us-east",
    "data_residency_plan": "Growth", "eu_region_city": "Dublin",
    # api
    "api_base": "https://api.relayline.dev/v2", "auth_header": "X-Relayline-Key",
    "signature_header": "Relayline-Signature", "signature_algo": "HMAC-SHA256",
    "signature_tolerance": "300 seconds", "idempotency_header": "Idempotency-Key",
    "idempotency_window": "24 hours", "pagination_param": "cursor", "page_max": "200",
    # errors
    "err_rate": "429", "err_payload": "413", "err_sig": "401", "err_dup": "409",
    "err_dead": "410", "dead_letter_days": "7",
    # sla / security
    "sla_uptime": "99.95%", "sla_credit": "10%", "sla_plan": "Growth",
    "soc2": "SOC 2 Type II", "encryption_rest": "AES-256", "key_rotation_days": "90",
    "sso_plan": "Growth", "audit_log_days": "365",
    # support
    "support_free": "community forum", "support_starter": "email, 2 business days",
    "support_growth": "email and chat, 4 business hours", "status_page": "status.relayline.dev",
    "founded_year": "2021", "legacy_starter_price": "$19", "legacy_starter_events": "100,000", "legacy_payload_max": "64 KB", "changelog_date": "March 2026", "hq_city": "Lisbon", "cli_name": "rl", "sdk_langs": "Go, Python, TypeScript, Ruby",
}

DOCS = {
"01-overview.md": """# Relayline overview
Relayline is a webhook relay service: your sources send events to Relayline, and Relayline delivers
them to your endpoints with retries, signatures and replay. The company was founded in {founded_year}
and is headquartered in {hq_city}. SDKs are available for {sdk_langs}. The command-line tool is `{cli_name}`.
Public status is published at {status_page}.
""",
"02-pricing.md": """# Pricing
All prices are in {currency}.
- **Free**: {free_events} events per month, {endpoints_free} endpoints, {free_retention_days}-day event retention.
- **Starter**: {starter_price} per month, {starter_events} events per month, {endpoints_starter} endpoints, {paid_retention_days}-day retention.
- **Growth**: {growth_price} per month, {growth_events} events per month, {endpoints_growth} endpoints, {paid_retention_days}-day retention.
Overage on paid plans is billed at {overage_per_1k} per 1,000 events. Annual billing gives a {annual_discount} discount.
""",
"03-limits.md": """# Limits and quotas
- Maximum payload size: {payload_max}. Larger requests are rejected with HTTP {err_payload}.
- Rate limit: {rate_limit_rps} requests per second sustained, bursts up to {burst_rps} requests per second.
  Exceeding it returns HTTP {err_rate}.
- Delivery timeout: an endpoint must respond within {timeout_seconds} seconds.
- Pagination: list endpoints accept a `{pagination_param}` parameter and return at most {page_max} items per page.
""",
"04-retries.md": """# Retries and dead letters
Failed deliveries are retried up to {max_retries} times with exponential backoff, starting at
{retry_backoff_base} and capped at {retry_backoff_cap}. After the last retry the event moves to the
dead-letter queue, where it is kept for {dead_letter_days} days and can be replayed from the dashboard or the CLI.
Replaying a dead-lettered event that has already expired returns HTTP {err_dead}.
""",
"05-regions.md": """# Regions and data residency
Relayline runs in three regions: {regions}. New accounts default to {default_region}.
The eu-west region is hosted in {eu_region_city}. Pinning an account to a single region (data residency)
is available on the {data_residency_plan} plan.
""",
"06-authentication.md": """# Authentication
The API base URL is {api_base}. Every request must carry the API key in the `{auth_header}` header.
Requests with a missing or invalid key return HTTP {err_sig}. API keys should be rotated at least every
{key_rotation_days} days; the dashboard shows the age of each key.
""",
"07-signatures.md": """# Verifying webhook signatures
Each delivery includes a `{signature_header}` header computed with {signature_algo} over the timestamp
and the raw body. Reject deliveries whose timestamp is older than {signature_tolerance} to prevent replay attacks.
A signature mismatch on your side should be treated as an unauthenticated request.
""",
"08-idempotency.md": """# Idempotency
Send an `{idempotency_header}` header to make event creation safe to retry. Relayline remembers keys for
{idempotency_window}; a repeated key with a different body inside that window returns HTTP {err_dup}.
""",
"09-retention.md": """# Event retention
Events are stored for {free_retention_days} days on the Free plan and {paid_retention_days} days on paid plans.
Audit logs are kept for {audit_log_days} days on every plan. After the retention period, event bodies are deleted
and only metadata remains.
""",
"10-sla.md": """# Service level agreement
The {sla_plan} plan includes an uptime commitment of {sla_uptime} per calendar month. If Relayline misses it,
the customer receives a service credit of {sla_credit} of that month's invoice. Free and Starter plans have no SLA.
""",
"11-security.md": """# Security
Relayline is {soc2} audited. Data at rest is encrypted with {encryption_rest}. Single sign-on (SSO) is available
on the {sla_plan} plan. Audit logs are retained for {audit_log_days} days.
""",
"12-support.md": """# Support
- Free: {support_free}.
- Starter: {support_starter}.
- Growth: {support_growth}.
Status incidents are posted at {status_page}.
""",
"13-cli.md": """# Command-line tool
Install the `{cli_name}` CLI from the releases page. Useful commands: `{cli_name} events list --{pagination_param} <token>`,
`{cli_name} deadletter replay <event-id>`, `{cli_name} keys rotate`. The CLI reads the API key from the
`RELAYLINE_KEY` environment variable and talks to {api_base}.
""",
"14-errors.md": """# Error reference
| Status | Meaning |
|---|---|
| {err_sig} | Missing or invalid API key, or bad signature |
| {err_dup} | Idempotency key reused with a different body |
| {err_dead} | Dead-lettered event expired (older than {dead_letter_days} days) |
| {err_payload} | Payload larger than {payload_max} |
| {err_rate} | Rate limit exceeded ({rate_limit_rps} rps sustained, {burst_rps} burst) |
""",
"15-faq.md": """# FAQ
**Can I change region later?** Yes, but only on the {data_residency_plan} plan; otherwise accounts stay in {default_region}.
**How many endpoints can I register?** {endpoints_free} on Free, {endpoints_starter} on Starter, {endpoints_growth} on Growth.
**Do you offer a discount?** Annual billing is {annual_discount} cheaper.
**Which languages have SDKs?** {sdk_langs}.
""",
"16-legacy-pricing-2024.md": """# Pricing (2024, deprecated)
> This page is kept for reference only. It no longer applies. See the current pricing page.
In 2024 the Starter plan cost {legacy_starter_price} per month for {legacy_starter_events} events, and the
maximum payload size was {legacy_payload_max}. Annual billing had no discount.
""",
"17-changelog.md": """# Changelog
- {changelog_date}: payload limit raised from {legacy_payload_max} to {payload_max}; Starter now includes
  {starter_events} events at {starter_price}; annual discount of {annual_discount} introduced.
- 2025: retries increased to {max_retries} attempts; ap-south region launched.
- 2024: initial release with us-east and eu-west.
""",
}

QUESTIONS = [
    ("q01", "How many events per month does the Free plan include?", "10,000|10000"),
    ("q02", "What does the Starter plan cost per month?", "$29|29"),
    ("q03", "How many events per month are included in the Growth plan?", "2,000,000|2 million|2000000"),
    ("q04", "What is the overage price per 1,000 events on paid plans?", "0.40"),
    ("q05", "What discount do I get for annual billing?", "17"),
    ("q06", "What is the maximum webhook payload size?", "256"),
    ("q07", "How many days are events retained on the Free plan?", "3"),
    ("q08", "How many days are events retained on paid plans?", "30"),
    ("q09", "How many times is a failed delivery retried?", "8"),
    ("q10", "What is the initial backoff delay between retries?", "5 second"),
    ("q11", "What is the maximum backoff delay between retries?", "2 hour"),
    ("q12", "How many endpoints can a Starter account register?", "25"),
    ("q13", "What is the sustained rate limit in requests per second?", "500"),
    ("q14", "What is the burst rate limit?", "2,000|2000"),
    ("q15", "Within how many seconds must an endpoint respond to a delivery?", "15"),
    ("q16", "Which regions does Relayline operate in?", "ap-south"),
    ("q17", "What is the default region for new accounts?", "us-east"),
    ("q18", "Which plan is required for data residency (single-region pinning)?", "Growth"),
    ("q19", "In which city is the eu-west region hosted?", "Dublin"),
    ("q20", "What is the API base URL?", "api.relayline.dev/v2"),
    ("q21", "Which HTTP header carries the API key?", "X-Relayline-Key"),
    ("q22", "Which header contains the webhook signature?", "Relayline-Signature"),
    ("q23", "Which algorithm is used for webhook signatures?", "HMAC-SHA256|HMAC SHA256|HMAC-SHA-256"),
    ("q24", "How old can a delivery timestamp be before it should be rejected?", "300|5 minutes|five minutes"),
    ("q25", "Which header makes event creation idempotent?", "Idempotency-Key"),
    ("q26", "For how long are idempotency keys remembered?", "24 hour"),
    ("q27", "What is the maximum number of items per page when listing events?", "200"),
    ("q28", "Which HTTP status is returned when the rate limit is exceeded?", "429"),
    ("q29", "Which HTTP status is returned for a payload that is too large?", "413"),
    ("q30", "Which HTTP status indicates an idempotency key was reused with a different body?", "409"),
    ("q31", "Which HTTP status is returned when replaying an expired dead-lettered event?", "410"),
    ("q32", "How many days are dead-lettered events kept?", "7"),
    ("q33", "What uptime does the SLA commit to?", "99.95"),
    ("q34", "What service credit is given when the SLA is missed?", "10%|10 percent"),
    ("q35", "Which compliance audit does Relayline hold?", "SOC 2"),
    ("q36", "How is data at rest encrypted?", "AES-256|AES 256"),
    ("q37", "How often should API keys be rotated?", "90"),
    ("q38", "For how many days are audit logs retained?", "365"),
    ("q39", "What support does the Growth plan include?", "chat"),
    ("q40", "In which city is Relayline headquartered?", "Lisbon"),
    # --- harder: stale vs current (legacy doc is a trap) ---
    ("q41", "What is the current monthly price of the Starter plan?", "29"),
    ("q42", "What is the current maximum payload size?", "256"),
    ("q43", "How many events does the Starter plan include today?", "250,000|250000"),
    # --- arithmetic from documented numbers ---
    ("q44", "If a Starter customer sends 300,000 events in a month, what is the overage charge in dollars?", "$20|20 dollars|20.00| 20"),
    ("q45", "What is the Starter plan's effective monthly price with annual billing, rounded to the nearest dollar?", "24"),
    ("q46", "What is the total yearly cost of the Growth plan on monthly billing?", "1,788|1788"),
    # --- negation / plan gating ---
    ("q47", "Does the Starter plan include an SLA?", "no|not|does not"),
    ("q48", "Can a Free plan account be pinned to the eu-west region?", "no|not|only on the growth|growth plan"),
    ("q49", "Is single sign-on available on the Starter plan?", "no|not|only on the growth|growth plan"),
    # --- not in the docs: the right answer is to say so ---
    ("q50", "What is Relayline's refund policy?", "not|no information|doesn't|does not|unable"),
    ("q51", "Does Relayline support SMS delivery of events?", "not|no information|doesn't|does not|unable"),
    ("q52", "What is the phone number for Relayline support?", "not|no information|doesn't|does not|unable"),
    ("q53", "Which database does Relayline use internally?", "not|no information|doesn't|does not|unable"),
    ("q54", "How many employees does Relayline have?", "not|no information|doesn't|does not|unable"),
    # --- multi-hop ---
    ("q55", "Which HTTP status would I get if I retry a replay of an event dead-lettered 10 days ago?", "410"),
    ("q56", "What is the longest total time a single delivery can spend in retries, roughly, given the retry schedule?", "hour"),
    ("q57", "Which region launched most recently?", "ap-south"),
    ("q58", "When was the payload limit raised, and from what size?", "64"),
    ("q59", "On which plan would a team that needs both SSO and data residency have to be?", "Growth"),
    ("q60", "A delivery arrives with a timestamp 10 minutes old. Should it be accepted?", "no|not|reject"),
]

def main():
    for name, body in DOCS.items():
        (CORPUS / name).write_text(body.format(**FACTS))
    with open(ROOT / "questions.jsonl", "w") as f:
        for qid, q, exp in QUESTIONS:
            f.write(json.dumps({"id": qid, "question": q, "expected_contains": exp}) + "\n")
    print(f"wrote {len(DOCS)} docs and {len(QUESTIONS)} questions")

if __name__ == "__main__":
    main()
