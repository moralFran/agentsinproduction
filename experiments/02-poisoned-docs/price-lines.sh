#!/usr/bin/env bash
# The Starter price line in the reviewed pricing page and in the planted 2027 page.
cd "$(dirname "$0")"
printf "reviewed  02-pricing.md               %s\n" "$(grep -o 'Starter\*\*: \$[0-9]* per month' corpus/02-pricing.md | tr -d '*')"
printf "planted   18-pricing-update-2027.md   %s\n" "$(grep -o 'Starter\*\*: \$[0-9]* per month' corpus-p1/18-pricing-update-2027.md | tr -d '*')"
