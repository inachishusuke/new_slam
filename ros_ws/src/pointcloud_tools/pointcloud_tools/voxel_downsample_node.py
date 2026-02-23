#!/usr/bin/env python3
"""Lightweight voxel-like downsampling node for PointCloud2 streams."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Dict, Tuple

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2


LOG_PATH = Path('/opt/lio_system/data/logs/voxel_downsample.log')


def build_logger() -> logging.Logger:
    logger = logging.getLogger('voxel_downsample')
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class VoxelDownsampleNode(Node):
    """Approximate voxel filter by hashing XYZ positions to voxel bins."""

    def __init__(self) -> None:
        super().__init__('voxel_downsample_node')
        self.logger = build_logger()
        self.declare_parameter('input_topic', '/lio/pointcloud_raw')
        self.declare_parameter('output_topic', '/lio/pointcloud_downsampled')
        self.declare_parameter('voxel_size', 0.2)
        self.declare_parameter('fallback_stride', 4)

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        self.voxel_size = float(self.get_parameter('voxel_size').value)
        self.fallback_stride = int(self.get_parameter('fallback_stride').value)

        self.publisher = self.create_publisher(PointCloud2, self.output_topic, 10)
        self.subscription = self.create_subscription(
            PointCloud2,
            self.input_topic,
            self._on_pointcloud,
            10,
        )
        self.logger.info(
            'Voxel downsample node started input=%s output=%s voxel=%.3f',
            self.input_topic,
            self.output_topic,
            self.voxel_size,
        )

    def _on_pointcloud(self, msg: PointCloud2) -> None:
        try:
            if msg.point_step <= 0 or not msg.data:
                self.logger.warning('Received invalid PointCloud2 frame')
                return

            points_total = len(msg.data) // msg.point_step
            if points_total < 2:
                self.publisher.publish(msg)
                return

            x_off, y_off, z_off = self._xyz_offsets(msg)
            if x_off is None:
                self.logger.warning('Missing xyz fields, applying stride fallback')
                self.publisher.publish(self._stride_downsample(msg, self.fallback_stride))
                return

            output = bytearray()
            occupied: Dict[Tuple[int, int, int], bytes] = {}
            for index in range(points_total):
                base = index * msg.point_step
                point_bytes = msg.data[base : base + msg.point_step]
                x = self._float_from_bytes(point_bytes[x_off : x_off + 4])
                y = self._float_from_bytes(point_bytes[y_off : y_off + 4])
                z = self._float_from_bytes(point_bytes[z_off : z_off + 4])
                key = (
                    math.floor(x / self.voxel_size),
                    math.floor(y / self.voxel_size),
                    math.floor(z / self.voxel_size),
                )
                if key not in occupied:
                    occupied[key] = bytes(point_bytes)

            for point in occupied.values():
                output.extend(point)

            downsampled = PointCloud2()
            downsampled.header = msg.header
            downsampled.height = 1
            downsampled.width = len(occupied)
            downsampled.fields = msg.fields
            downsampled.is_bigendian = msg.is_bigendian
            downsampled.point_step = msg.point_step
            downsampled.row_step = downsampled.point_step * downsampled.width
            downsampled.data = bytes(output)
            downsampled.is_dense = msg.is_dense

            self.publisher.publish(downsampled)
        except Exception as exc:
            self.logger.exception('Downsample failed: %s', exc)

    @staticmethod
    def _xyz_offsets(msg: PointCloud2) -> Tuple[int | None, int | None, int | None]:
        offsets = {'x': None, 'y': None, 'z': None}
        for field in msg.fields:
            if field.name in offsets:
                offsets[field.name] = field.offset
        return offsets['x'], offsets['y'], offsets['z']

    @staticmethod
    def _float_from_bytes(chunk: bytes) -> float:
        import struct

        return struct.unpack('f', chunk)[0]

    @staticmethod
    def _stride_downsample(msg: PointCloud2, stride: int) -> PointCloud2:
        out = PointCloud2()
        out.header = msg.header
        out.height = 1
        out.fields = msg.fields
        out.is_bigendian = msg.is_bigendian
        out.point_step = msg.point_step
        out.is_dense = msg.is_dense
        raw = bytearray()
        points_total = len(msg.data) // msg.point_step
        for index in range(0, points_total, max(stride, 1)):
            base = index * msg.point_step
            raw.extend(msg.data[base : base + msg.point_step])
        out.width = len(raw) // msg.point_step
        out.row_step = out.width * out.point_step
        out.data = bytes(raw)
        return out


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VoxelDownsampleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
