#!/usr/bin/env bash
# Sourced by create.sh, list.sh and destroy.sh: the one definition of what belongs to this experiment in GCP.
# Instances are selected by the aip- prefix AND the labels owner=aip AND experiment=aip-v04-kata. destroy.sh deletes
# instances only (their disks go with them) and refuses any selected name that is not in AIP_EXPECTED.
# Disks are only ever LISTED, and by the two exact names (a boot disk is named after its instance): `instances
# create --labels` labels the instance, not its disk, so a label filter on disks could come back empty with a disk
# still there. create.sh labels the disks afterwards as well; the listing does not depend on that having worked.
# ("v04" is the video's production id; this is experiment 03 of the channel. See the README.)
AIP_LABELS='owner=aip,experiment=aip-v04-kata'
AIP_F='name~^aip- AND labels.owner=aip AND labels.experiment=aip-v04-kata'
AIP_EXPECTED="aip-endpoint-01 aip-kata-01"
AIP_DISKS_F='name=aip-endpoint-01 OR name=aip-kata-01'
