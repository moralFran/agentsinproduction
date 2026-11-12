#!/usr/bin/env bash
# Lists what this experiment created, in the explicit project. Instances: the filter destroy.sh deletes by (prefix
# and both labels, infra/scope.sh). Disks: this experiment's two disk names, labelled or not, because a disk does not
# inherit its instance's labels. "none" twice means nothing is left.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
. "$(dirname "$0")/scope.sh"
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1 CLOUDSDK_CORE_SURVEY_DISABLE_PROMPTS=1   # no gcloud notices in the output
L() { gcloud compute instances list --project "$AIP_PROJECT" --filter="$AIP_F" --verbosity=error "$@"; }
if [ -z "$(L --format='value(name)')" ]; then echo "instances: none"; else
  L --format='table(name, machineType.basename():label=MACHINE, status, labels.owner:label=OWNER, labels.experiment:label=EXPERIMENT)'
  echo
  L --format='table(name, advancedMachineFeatures.enableNestedVirtualization:label=NESTED_VIRT, guestAccelerators.len():label=GPUS, serviceAccounts.len():label=SERVICE_ACCOUNTS)'
  echo
fi
d=$(gcloud compute disks list --project "$AIP_PROJECT" --filter="$AIP_DISKS_F" --format='value(name)' --verbosity=error | tr '\n' ' ')
echo "disks: ${d:-none}"
