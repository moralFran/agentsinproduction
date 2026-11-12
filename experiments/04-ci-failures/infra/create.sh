#!/usr/bin/env bash
# Creates the ephemeral VM of experiment 04 (30 real CI failures). Name aip-ci-01, labels owner=aip AND
# experiment=aip-v05-ci, no service account (the metadata server has no GCP token to hand out), nested virtualization
# for Kata, no GPU. The project is explicit; the gcloud default is never used.
set -euo pipefail
: "${AIP_PROJECT:?set AIP_PROJECT to the GCP project id}"
ZONE="${ZONE:-us-central1-a}"
gcloud compute instances create aip-ci-01 --project "$AIP_PROJECT" --zone "$ZONE" \
  --labels owner=aip,experiment=aip-v05-ci --no-service-account --no-scopes \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --machine-type n2-standard-8 --enable-nested-virtualization --boot-disk-size 200GB --boot-disk-type pd-balanced
ip() { gcloud compute instances describe "$1" --project "$AIP_PROJECT" --zone "$ZONE" --format='value(networkInterfaces[0].networkIP)'; }
printf 'ZONE=%s\nNODE_IP=%s\n' "$ZONE" "$(ip aip-ci-01)" > "$(dirname "$0")/../lab.env"
cat "$(dirname "$0")/../lab.env"
