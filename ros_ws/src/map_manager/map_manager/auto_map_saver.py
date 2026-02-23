#!/usr/bin/env python3
"""Periodic and on-demand map saver for FAST-LIO maps."""

from __future__ import annotations

import datetime as dt
import logging
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
        self.declare_parameter('map_save_service', '/map_save')
        self.declare_parameter('save_timeout_sec', 20.0)

        self.map_dir = Path(str(self.get_parameter('map_dir').value))
        self.save_interval_sec = float(self.get_parameter('save_interval_sec').value)
        self.map_save_service = str(self.get_parameter('map_save_service').value)
        self.save_timeout_sec = float(self.get_parameter('save_timeout_sec').value)

        self.map_dir.mkdir(parents=True, exist_ok=True)
        self.map_save_client = self.create_client(Trigger, self.map_save_service)
        self.timer = self.create_timer(self.save_interval_sec, self.periodic_save)
        self.service = self.create_service(Trigger, 'manual_map_save', self.manual_save)

        self.logger.info(
            'Auto map saver active interval=%.1fs service=%s timeout=%.1fs',
            self.save_interval_sec,
            self.map_save_service,
            self.save_timeout_sec,
        )

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
        meta_file = output_file.with_suffix(output_file.suffix + '.meta')

        if not self.map_save_client.wait_for_service(timeout_sec=2.0):
            msg = f'map save service unavailable: {self.map_save_service}'
            self.logger.error(msg)
            meta_file.write_text(f'{msg}\n', encoding='utf-8')
            return False, msg

        request = Trigger.Request()
        future = self.map_save_client.call_async(request)

        try:
            rclpy.spin_until_future_complete(self, future, timeout_sec=self.save_timeout_sec)
            response = future.result()
            if response is None:
                msg = f'map save service timeout after {self.save_timeout_sec:.1f}s'
                self.logger.error(msg)
                meta_file.write_text(f'{msg}\n', encoding='utf-8')
                return False, msg

            message = response.message or ''
            meta_file.write_text(
                f'service={self.map_save_service}\n'
                f'success={response.success}\n'
                f'message={message}\n',
                encoding='utf-8',
            )

            if not response.success:
                msg = f'map save service returned failure: {message}'
                self.logger.error(msg)
                return False, msg

            output_file.touch(exist_ok=True)
            msg = f'map saved ({reason}) {output_file.name}'
            self.logger.info(msg)
            return True, msg
        except Exception as exc:
            msg = f'map save failed: {exc}'
            self.logger.exception(msg)
            meta_file.write_text(f'{msg}\n', encoding='utf-8')
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
