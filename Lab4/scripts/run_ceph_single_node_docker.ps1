$ErrorActionPreference = "Stop"

$lab4 = "\\wsl.localhost\Ubuntu-24.04\home\qy-dream\OSH_Project\KVFabric\Lab4"
$image = "quay.io/ceph/daemon:latest-quincy"
$name = "lab4-ceph-single"

try {
  docker rm -f $name 2>$null | Out-Null
} catch {
}
docker run --rm --privileged --name $name `
  -v "${lab4}:/lab4" `
  -e OUT_DIR="/lab4/results/ceph/single_docker" `
  -e OSD_COUNT="1" `
  -e POOL_SIZE="1" `
  --entrypoint bash `
  $image -lc "bash /lab4/scripts/ceph_single_node_inside.sh"
