#!/usr/bin/env python3
"""Industrial full-stack bringup launch for Raspberry Pi 5."""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    data_root = LaunchConfiguration('data_root')
    start_recording = LaunchConfiguration('start_recording')
    fastlio_launch = LaunchConfiguration('fastlio_launch')

    return LaunchDescription(
        [
            DeclareLaunchArgument('data_root', default_value='/opt/lio_system/data'),
            DeclareLaunchArgument('start_recording', default_value='false'),
            DeclareLaunchArgument('fastlio_launch', default_value='/opt/lio_system/ros_ws/src/FAST_LIO/launch/mapping.launch.py'),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(fastlio_launch)),
            Node(
                package='pointcloud_tools',
                executable='voxel_downsample_node',
                name='voxel_downsample_node',
                output='screen',
                parameters=[
                    {
                        'input_topic': '/lio/pointcloud_raw',
                        'output_topic': '/lio/pointcloud_downsampled',
                        'voxel_size': 0.25,
                    }
                ],
            ),
            Node(
                package='map_manager',
                executable='auto_map_saver',
                name='auto_map_saver',
                output='screen',
                parameters=[
                    {
                        'map_dir': [data_root, '/maps'],
                        'save_interval_sec': 30.0,
                    }
                ],
            ),
            ExecuteProcess(
                cmd=[
                    'ros2',
                    'bag',
                    'record',
                    '-a',
                    '-o',
                    [data_root, '/rosbag/auto_recording'],
                ],
                condition=IfCondition(start_recording),
                output='screen',
            ),
            ExecuteProcess(
                cmd=['python3', '/opt/lio_system/backend/main.py'],
                output='screen',
            ),
        ]
    )
