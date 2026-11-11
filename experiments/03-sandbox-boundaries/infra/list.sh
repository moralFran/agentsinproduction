#!/usr/bin/env bash
# Lists what this experiment created: only resources labelled experiment=aip-v04-kata, in the explicit project.
# The same filter the destroy script acts on. An empty table means nothing is left.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1 CLOUDSDK_CORE_SURVEY_DISABLE_PROMPTS=1   # no gcloud notices in the output
F='labels.owner=aip AND labels.experiment=aip-v04-kata'
L() { gcloud compute instances list --project "$AIP_PROJECT" --filter="$F" --verbosity=error "$@"; }
if [ -z "$(L --format='value(name)')" ]; then echo "instances: none"; else
  L --format='table(name, machineType.basename():label=MACHINE, status, labels.owner:label=OWNER, labels.experiment:label=EXPERIMENT)'
  echo
  L --format='table(name, advancedMachineFeatures.enableNestedVirtualization:label=NESTED_VIRT, guestAccelerators.len():label=GPUS, serviceAccounts.len():label=SERVICE_ACCOUNTS)'
  echo
fi
d=$(gcloud compute disks list --project "$AIP_PROJECT" --filter="name~^aip-" --format='value(name)' --verbosity=error | tr '\n' ' ')
echo "disks: ${d:-none}"
