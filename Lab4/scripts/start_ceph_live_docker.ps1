$ErrorActionPreference = "Stop"

$lab4 = "\\wsl.localhost\Ubuntu-24.04\home\qy-dream\OSH_Project\KVFabric\Lab4"
$image = "quay.io/ceph/daemon:latest-quincy"
$name = "lab4-ceph-live"

try {
  docker rm -f $name 2>$null | Out-Null
} catch {
}

docker run -d --privileged --name $name `
  -v "${lab4}:/lab4" `
  -e OUT_DIR="/lab4/results/ray_ceph/live_ceph" `
  -e OSD_COUNT="3" `
  -e POOL_SIZE="2" `
  -e SKIP_BENCH="1" `
  -e KEEPALIVE="1" `
  --entrypoint bash `
  $image -lc "bash /lab4/scripts/ceph_single_node_inside.sh"

for ($i = 0; $i -lt 90; $i++) {
  $status = docker exec $name ceph -s 2>$null
  if ($LASTEXITCODE -eq 0 -and $status -match "3 osds: 3 up") {
    Write-Output $status
    exit 0
  }
  Start-Sleep -Seconds 2
}

docker logs --tail 120 $name
throw "Ceph live container did not become ready"
