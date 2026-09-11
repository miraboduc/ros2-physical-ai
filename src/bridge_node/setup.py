from setuptools import find_packages, setup
import os
from glob import glob

package_name = "bridge_node"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Hoang Duc",
    maintainer_email="duchv@mirabo-global.com",
    description="Vision-to-motion bridge node connecting yolo_ros detections to fanuc_moveit_config motion",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "bridge_node = bridge_node.bridge_node:main",
        ],
    },
)
