"""ROS lifecycle management for industrial LIO system."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional


class RosManager:
    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.ros_process: Optional[subprocess.Popen] = None
        self.record_process: Optional[subprocess.Popen] = None
        self.recording_start_epoch: float | None = None

    def start_ros(self) -> None:
        if self.is_ros_running():
            self.logger.info('ROS already running')
            return
        command = ['bash', '-lc', self.config['ros_launch_cmd']]
        self.logger.info('Starting ROS launch')
        self.ros_process = subprocess.Popen(command, preexec_fn=os.setsid)

    def stop_ros(self) -> None:
        if not self.ros_process:
            return
        self.logger.info('Stopping ROS launch')
        self._terminate_process_group(self.ros_process)
        self.ros_process = None

    def restart_ros(self) -> None:
        self.logger.warning('Restarting ROS launch')
        self.stop_ros()
        time.sleep(2)
        self.start_ros()

    def is_ros_running(self) -> bool:
        return self.ros_process is not None and self.ros_process.poll() is None

    def is_recording(self) -> bool:
        return self.record_process is not None and self.record_process.poll() is None

    def recording_duration_sec(self) -> int:
        if not self.is_recording() or self.recording_start_epoch is None:
            return 0
        return max(0, int(time.time() - self.recording_start_epoch))

    def start_recording(self) -> tuple[bool, str]:
        if self.is_recording():
            return False, 'Recording already active'
        stamp = int(time.time())
        output_prefix = Path(self.config['rosbag_dir']) / f'bag_{stamp}'
        output_prefix.parent.mkdir(parents=True, exist_ok=True)
        cmd = f"source /opt/ros/humble/setup.bash && ros2 bag record {self.config['record_topics']} -o {output_prefix}"
        self.logger.info('Starting rosbag recording to %s', output_prefix)
        self.record_process = subprocess.Popen(['bash', '-lc', cmd], preexec_fn=os.setsid)
        self.recording_start_epoch = time.time()
        return True, f'Started recording {output_prefix}'

    def stop_recording(self) -> tuple[bool, str]:
        if not self.is_recording():
            self.record_process = None
            self.recording_start_epoch = None
            return False, 'Recording is not active'
        self.logger.info('Stopping rosbag recording')
        self._terminate_process_group(self.record_process)
        self.record_process = None
        self.recording_start_epoch = None
        return True, 'Recording stopped'

    def save_map(self) -> tuple[bool, str]:
        cmd = 'source /opt/ros/humble/setup.bash && ros2 service call /manual_map_save std_srvs/srv/Trigger {}'
        try:
            result = subprocess.run(['bash', '-lc', cmd], check=False, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                self.logger.error('Manual map save failed: %s', result.stderr.strip())
                return False, 'Manual map save failed'
            return True, result.stdout.strip() or 'Map save requested'
        except Exception as exc:
            self.logger.exception('Manual map save exception: %s', exc)
            return False, str(exc)

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen, timeout: int = 8) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
