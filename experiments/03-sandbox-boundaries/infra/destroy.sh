#!/usr/bin/env bash
# Deletes ONLY this experiment's two VMs (and their disks), in an explicit project, and only if each still carries the
# aip- prefix, owner=aip and experiment=aip-v04-kata (infra/scope.sh). Other aip-* resources are never selected.
# Prints what is left: instances by the same filter, disks by this experiment's two names.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
. "$(dirname "$0")/scope.sh"
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1 CLOUDSDK_CORE_SURVEY_DISABLE_PROMPTS=1
F="$AIP_F"; EXPECTED="$AIP_EXPECTED"
found=$(gcloud compute instances list --project "$AIP_PROJECT" --filter="$F" --format="value(name)" | sort | tr '\n' ' ')
echo "selected: ${found:-none}"
for n in $found; do case " $EXPECTED " in *" $n "*) ;; *) echo "refusing: unexpected instance $n"; exit 1;; esac; done
gcloud compute instances list --project "$AIP_PROJECT" --filter="$F" --format="value(name,zone)" | while read -r n z; do
  # gcloud's own message carries the full resource URL (project id included): print a short line, keep the error if any
  if out=$(gcloud compute instances delete "$n" --project "$AIP_PROJECT" --zone "$z" --delete-disks=all --quiet 2>&1); then echo "deleted: $n (and its disks)"; else echo "$out"; exit 1; fi
done
echo "left (instances): $(gcloud compute instances list --project "$AIP_PROJECT" --filter="$F" --format='value(name)' --verbosity=error | tr '\n' ' ')"
echo "left (disks):     $(gcloud compute disks list --project "$AIP_PROJECT" --filter="$AIP_DISKS_F" --format='value(name)' --verbosity=error | tr '\n' ' ')"
