from setuptools import setup

package_name = 'pointcloud_tools'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'numpy'],
    zip_safe=True,
    maintainer='ops',
    maintainer_email='ops@example.com',
    description='Pointcloud processing tools for industrial LIO system.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'voxel_downsample_node = pointcloud_tools.voxel_downsample_node:main',
        ],
    },
)
