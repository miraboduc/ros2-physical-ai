from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    enable_on_start = DeclareLaunchArgument("enable_on_start", default_value="true")

    bridge_node = Node(
        package="bridge_node",
        executable="bridge_node",
        name="bridge_node",
        output="screen",
        parameters=[{"enable_on_start": LaunchConfiguration("enable_on_start")}],
    )

    return LaunchDescription([enable_on_start, bridge_node])
