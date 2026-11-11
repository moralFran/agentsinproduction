#!/usr/bin/env bash
# Creates the two ephemeral VMs of experiment 03 (sandbox boundaries) and writes lab.env with their addresses.
# Names are aip-*, labels are owner=aip AND experiment=aip-v04-kata. No service account on either VM: the metadata
# server has no GCP token to hand out. The project is explicit; the gcloud default is never used.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
ZONE="${ZONE:-us-central1-a}"
COMMON=(--project "$AIP_PROJECT" --zone "$ZONE" --labels owner=aip,experiment=aip-v04-kata --no-service-account --no-scopes
        --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud)
# The lab: k3s + Kata. Nested virtualization so Kata can start a guest VM.
gcloud compute instances create aip-kata-01 "${COMMON[@]}" --machine-type n2-standard-4 \
  --enable-nested-virtualization --boot-disk-size 50GB --boot-disk-type pd-balanced
# The "outside world": a test endpoint we control, reached over the VPC's internal network.
gcloud compute instances create aip-endpoint-01 "${COMMON[@]}" --machine-type e2-micro \
  --boot-disk-size 10GB --boot-disk-type pd-standard
ip() { gcloud compute instances describe "$1" --project "$AIP_PROJECT" --zone "$ZONE" --format='value(networkInterfaces[0].networkIP)'; }
printf 'ZONE=%s\nNODE_IP=%s\nENDPOINT_IP=%s\n' "$ZONE" "$(ip aip-kata-01)" "$(ip aip-endpoint-01)" > "$(dirname "$0")/../lab.env"
cat "$(dirname "$0")/../lab.env"
