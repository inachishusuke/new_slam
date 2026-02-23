"""Application watchdog for ROS health supervision."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Callable

from ros_manager import RosManager


class WatchdogMonitor:
    ROS2_NODE_LIST_CMD = ['/opt/ros/humble/bin/ros2', 'node', 'list']

    def __init__(
        self,
        config: dict,
        ros_manager: RosManager,
        logger: logging.Logger,
        on_fault: Callable[[str], None],
    ) -> None:
        self.interval = float(config['watchdog_interval_sec'])
        self.ros_manager = ros_manager
        self.logger = logger
        self.on_fault = on_fault
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        self.logger.info('Watchdog monitor started')
        while not self._stop_event.is_set():
            try:
                if not self.ros_manager.is_ros_running():
                    self.logger.error('ROS process not running')
                    self.on_fault('ros_process_down')
                elif not self._ros_nodes_responsive():
                    self.logger.error('ROS node health check failed')
                    self.on_fault('ros_nodes_unresponsive')
            except Exception as exc:
                self.logger.exception('Watchdog loop exception: %s', exc)
            self._stop_event.wait(self.interval)

    def _ros_nodes_responsive(self) -> bool:
        result = subprocess.run(
            self.ROS2_NODE_LIST_CMD,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            self.logger.warning('ros2 node list failed rc=%s stderr=%s', result.returncode, (result.stderr or '').strip())
            return False
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return len(lines) > 0
