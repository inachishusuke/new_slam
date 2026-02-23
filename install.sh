#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/lio_system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt-get update
sudo apt-get install -y \
  python3-pip python3-venv python3-colcon-common-extensions \
  ros-humble-rclpy ros-humble-sensor-msgs ros-humble-std-srvs \
  ros-humble-launch ros-humble-launch-ros \
  ros-humble-pcl-ros ros-humble-tf2-ros \
  smartmontools watchdog rsync curl

python3 -m pip install --upgrade pip
python3 -m pip install fastapi uvicorn pyyaml requests

"${SCRIPT_DIR}/scripts/setup_directories.sh"

sudo rsync -a --delete "${SCRIPT_DIR}/backend/" "${ROOT_DIR}/backend/"
sudo rsync -a --delete "${SCRIPT_DIR}/frontend/" "${ROOT_DIR}/frontend/"
sudo rsync -a --delete "${SCRIPT_DIR}/ros_ws/" "${ROOT_DIR}/ros_ws/"

pushd "${ROOT_DIR}/ros_ws" >/dev/null
source /opt/ros/humble/setup.bash
colcon build --symlink-install
popd >/dev/null

sudo cp "${SCRIPT_DIR}/systemd/lio_system.service" /etc/systemd/system/lio_system.service
sudo cp "${SCRIPT_DIR}/systemd/watchdog.conf" /etc/watchdog.conf

sudo systemctl daemon-reload
sudo systemctl enable lio_system.service
sudo systemctl restart lio_system.service

sudo systemctl enable watchdog
sudo systemctl restart watchdog

echo "Installation complete. Service: lio_system.service"
echo "Note: Install FAST_LIO and livox_ros_driver2 source trees under /opt/lio_system/ros_ws/src before build."
