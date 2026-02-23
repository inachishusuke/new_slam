#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/lio_system"

mkdir -p "${ROOT_DIR}/backend" \
         "${ROOT_DIR}/frontend" \
         "${ROOT_DIR}/ros_ws/src" \
         "${ROOT_DIR}/data/maps" \
         "${ROOT_DIR}/data/rosbag" \
         "${ROOT_DIR}/data/logs"

chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "${ROOT_DIR}"
chmod -R 775 "${ROOT_DIR}/data"

echo "Directory structure created under ${ROOT_DIR}"
