#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${OUT_DIR:-/lab4/results/ceph/single_docker}"
POOL="${POOL:-lab4bench}"
BENCH_SECONDS="${BENCH_SECONDS:-20}"
THREADS_BASELINE="${THREADS_BASELINE:-1}"
THREADS_OPT="${THREADS_OPT:-16}"
OBJ_SIZE="${OBJ_SIZE:-4194304}"
OSD_COUNT="${OSD_COUNT:-1}"
POOL_SIZE="${POOL_SIZE:-1}"
KEEPALIVE="${KEEPALIVE:-0}"
SKIP_BENCH="${SKIP_BENCH:-0}"

mkdir -p "$OUT_DIR"
rm -rf /etc/ceph/* /var/lib/ceph/mon/* /var/lib/ceph/mgr/* /var/lib/ceph/osd/*

FSID="$(uuidgen)"
MON_ID="a"
MGR_ID="a"
HOST="$(hostname -s)"

mkdir -p \
  /etc/ceph \
  "/var/lib/ceph/mon/ceph-${MON_ID}" \
  "/var/lib/ceph/mgr/ceph-${MGR_ID}" \
  /var/lib/ceph/osd \
  /var/run/ceph

cat > /etc/ceph/ceph.conf <<EOF
[global]
fsid = ${FSID}
mon initial members = ${MON_ID}
mon host = 127.0.0.1
public network = 127.0.0.0/8
auth cluster required = cephx
auth service required = cephx
auth client required = cephx
osd pool default size = 1
osd pool default min size = 1
mon warn on pool no redundancy = false
mon allow pool delete = true
mon allow pool size one = true
mon osd min in ratio = 0
osd crush chooseleaf type = 0
log to file = false
mon cluster log to file = false
EOF

ceph-authtool --create-keyring /tmp/ceph.mon.keyring --gen-key -n mon. --cap mon 'allow *'
ceph-authtool --create-keyring /etc/ceph/ceph.client.admin.keyring \
  --gen-key -n client.admin \
  --cap mon 'allow *' --cap osd 'allow *' --cap mgr 'allow *' --cap mds 'allow *'
ceph-authtool --create-keyring "/var/lib/ceph/mgr/ceph-${MGR_ID}/keyring" \
  --gen-key -n "mgr.${MGR_ID}" \
  --cap mon 'allow profile mgr' --cap osd 'allow *' --cap mds 'allow *'
ceph-authtool /tmp/ceph.mon.keyring --import-keyring /etc/ceph/ceph.client.admin.keyring
ceph-authtool /tmp/ceph.mon.keyring --import-keyring "/var/lib/ceph/mgr/ceph-${MGR_ID}/keyring"

monmaptool --create --add "${MON_ID}" 127.0.0.1 --fsid "${FSID}" /tmp/monmap
ceph-mon --mkfs -i "${MON_ID}" --monmap /tmp/monmap --keyring /tmp/ceph.mon.keyring
chown -R ceph:ceph /var/lib/ceph /var/run/ceph /etc/ceph

ceph-mon -i "${MON_ID}" --public-addr 127.0.0.1:6789 --setuser ceph --setgroup ceph \
  --default-log-to-file=false --default-mon-cluster-log-to-file=false \
  > "${OUT_DIR}/ceph-mon.log" 2>&1 &
MON_PID=$!

for _ in $(seq 1 60); do
  if ceph -s >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

ceph-mgr -i "${MGR_ID}" --setuser ceph --setgroup ceph \
  --default-log-to-file=false > "${OUT_DIR}/ceph-mgr.log" 2>&1 &
MGR_PID=$!

OSD_PIDS=()
for OSD_ID in $(seq 0 $((OSD_COUNT - 1))); do
  OSD_UUID="$(uuidgen)"
  mkdir -p "/var/lib/ceph/osd/ceph-${OSD_ID}"
  ceph osd create "${OSD_UUID}" "${OSD_ID}"
  ceph-authtool --create-keyring "/var/lib/ceph/osd/ceph-${OSD_ID}/keyring" \
    --gen-key -n "osd.${OSD_ID}" \
    --cap mon 'allow profile osd' --cap osd 'allow *' --cap mgr 'allow profile osd'
  ceph auth add "osd.${OSD_ID}" -i "/var/lib/ceph/osd/ceph-${OSD_ID}/keyring"
  chown -R ceph:ceph "/var/lib/ceph/osd/ceph-${OSD_ID}"
  ceph-osd -i "${OSD_ID}" --osd-uuid "${OSD_UUID}" --mkfs --setuser ceph --setgroup ceph
  chown -R ceph:ceph "/var/lib/ceph/osd/ceph-${OSD_ID}"
  ceph-osd -i "${OSD_ID}" --setuser ceph --setgroup ceph \
    --default-log-to-file=false > "${OUT_DIR}/ceph-osd.${OSD_ID}.log" 2>&1 &
  OSD_PIDS+=("$!")
  ceph osd crush add "osd.${OSD_ID}" 1.0 "root=default" "host=${HOST}" || true
done

for _ in $(seq 1 90); do
  if ceph health | grep -Eq 'HEALTH_OK|HEALTH_WARN'; then
    if ceph osd stat | grep -q "${OSD_COUNT} up"; then
      break
    fi
  fi
  sleep 1
done

ceph osd pool create "${POOL}" 32 32
ceph osd pool application enable "${POOL}" rados
ceph config set mon mon_allow_pool_size_one true || true
ceph osd pool set "${POOL}" size "${POOL_SIZE}" --yes-i-really-mean-it
ceph osd pool set "${POOL}" min_size 1

ceph -s > "${OUT_DIR}/ceph_status.txt"
ceph osd tree > "${OUT_DIR}/ceph_osd_tree.txt"
ceph osd df > "${OUT_DIR}/ceph_osd_df.txt"
ceph pg stat > "${OUT_DIR}/ceph_pg_stat.txt"
ceph tell "osd.0" bench > "${OUT_DIR}/ceph_osd_bench.txt" || true

if [ "${SKIP_BENCH}" != "1" ]; then
  rados bench -p "${POOL}" "${BENCH_SECONDS}" write -t "${THREADS_BASELINE}" -b "${OBJ_SIZE}" --no-cleanup \
    > "${OUT_DIR}/rados_write_t${THREADS_BASELINE}.txt"
  rados bench -p "${POOL}" "${BENCH_SECONDS}" seq -t "${THREADS_BASELINE}" \
    > "${OUT_DIR}/rados_seq_t${THREADS_BASELINE}.txt"
  rados bench -p "${POOL}" "${BENCH_SECONDS}" rand -t "${THREADS_BASELINE}" \
    > "${OUT_DIR}/rados_rand_t${THREADS_BASELINE}.txt"
  rados cleanup -p "${POOL}" --prefix benchmark_data || true

  rados bench -p "${POOL}" "${BENCH_SECONDS}" write -t "${THREADS_OPT}" -b "${OBJ_SIZE}" --no-cleanup \
    > "${OUT_DIR}/rados_write_t${THREADS_OPT}.txt"
  rados bench -p "${POOL}" "${BENCH_SECONDS}" seq -t "${THREADS_OPT}" \
    > "${OUT_DIR}/rados_seq_t${THREADS_OPT}.txt"
  rados bench -p "${POOL}" "${BENCH_SECONDS}" rand -t "${THREADS_OPT}" \
    > "${OUT_DIR}/rados_rand_t${THREADS_OPT}.txt"
  rados cleanup -p "${POOL}" --prefix benchmark_data || true
fi

ceph -s > "${OUT_DIR}/ceph_status_after_bench.txt"
PROCESS_PIDS="${MON_PID},${MGR_PID}"
for pid in "${OSD_PIDS[@]}"; do
  PROCESS_PIDS="${PROCESS_PIDS},${pid}"
done
ps -p "${PROCESS_PIDS}" -o pid,comm,args > "${OUT_DIR}/ceph_processes.txt" || true

echo "Ceph single-node Docker experiment finished: ${OUT_DIR}"

if [ "${KEEPALIVE}" = "1" ]; then
  tail -f /dev/null
fi
