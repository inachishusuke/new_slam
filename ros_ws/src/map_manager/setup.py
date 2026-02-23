from setuptools import setup

package_name = 'map_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ops',
    maintainer_email='ops@example.com',
    description='Map persistence helpers for industrial LIO system.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'auto_map_saver = map_manager.auto_map_saver:main',
        ],
    },
)
