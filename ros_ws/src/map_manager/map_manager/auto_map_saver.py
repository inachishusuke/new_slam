#!/usr/bin/env python3
"""Periodic and on-demand map saver for FAST-LIO maps."""

from __future__ import annotations

import datetime as dt
import logging
import subprocess
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

LOG_PATH = Path('/opt/lio_system/data/logs/auto_map_saver.log')


def build_logger() -> logging.Logger:
    logger = logging.getLogger('auto_map_saver')
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())
    return logger


class AutoMapSaver(Node):
    def __init__(self) -> None:
        super().__init__('auto_map_saver')
        self.logger = build_logger()
        self.declare_parameter('map_dir', '/opt/lio_system/data/maps')
        self.declare_parameter('save_interval_sec', 30.0)
        self.declare_parameter('save_command', 'ros2 service call /map_save std_srvs/srv/Trigger {}')

        self.map_dir = Path(str(self.get_parameter('map_dir').value))
        self.save_interval_sec = float(self.get_parameter('save_interval_sec').value)
        self.save_command = str(self.get_parameter('save_command').value)

        self.map_dir.mkdir(parents=True, exist_ok=True)
        self.timer = self.create_timer(self.save_interval_sec, self.periodic_save)
        self.service = self.create_service(Trigger, 'manual_map_save', self.manual_save)
        self.logger.info('Auto map saver active interval=%.1fs', self.save_interval_sec)

    def periodic_save(self) -> None:
        self._save_map('periodic')

    def manual_save(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        success, message = self._save_map('manual')
        response.success = success
        response.message = message
        return response

    def _save_map(self, reason: str) -> tuple[bool, str]:
        stamp = dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_file = self.map_dir / f'map_{reason}_{stamp}.pcd'
        command = f"{self.save_command} > {output_file}.meta 2>&1"
        try:
            result = subprocess.run(command, shell=True, check=False, timeout=20)
            if result.returncode != 0:
                msg = f'map save command failed rc={result.returncode}'
                self.logger.error(msg)
                return False, msg
            output_file.touch(exist_ok=True)
            msg = f'map saved ({reason}) {output_file.name}'
            self.logger.info(msg)
            return True, msg
        except subprocess.TimeoutExpired:
            msg = 'map save command timed out'
            self.logger.error(msg)
            return False, msg
        except Exception as exc:
            msg = f'map save failed: {exc}'
            self.logger.exception(msg)
            return False, msg


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = AutoMapSaver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._save_map('shutdown')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
