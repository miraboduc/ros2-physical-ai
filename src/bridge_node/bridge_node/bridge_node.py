"""COMP-BR-00 — BridgeNode.

Wires PoseConverter (COMP-BR-01), MotionGoalSender (COMP-BR-02) and
EnableGate (COMP-BR-03) together per docs/design/DDB-bridge-node.md.

Open issues carried into this implementation (not fully closed — see
docs/design/DDB-bridge-node.md §12 for the tracked ones; `table_height`,
`grasp_orientation_rpy` and `camera_frame` below are NEW placeholder
parameters discovered while implementing PoseConverter's 2D->3D math,
not yet in the reviewed design doc — they need a real value from actual
hardware/setup measurement, not a guess. Defaults here are placeholders
that make the node runnable, not physically-verified numbers.
"""

import math

from geometry_msgs.msg import Quaternion
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
import rclpy
import tf2_ros
from moveit_msgs.action import MoveGroup
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import String
from std_srvs.srv import SetBool
from yolo_msgs.msg import DetectionArray

from bridge_node.enable_gate import EnableGate
from bridge_node.motion_goal_sender import MotionGoalSender
from bridge_node.pose_converter import PoseConverter


def rpy_to_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return Quaternion(
        x=sr * cp * cy - cr * sp * sy,
        y=cr * sp * cy + sr * cp * sy,
        z=cr * cp * sy - sr * sp * cy,
        w=cr * cp * cy + sr * sp * sy,
    )


class BridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("bridge_node")

        self.declare_parameter("score_threshold", 0.5)
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("camera_frame", "camera_link")
        self.declare_parameter("table_height", 0.0)
        self.declare_parameter("grasp_orientation_rpy", [0.0, 0.0, 0.0])
        self.declare_parameter("workspace_bounds", [-1.0, 1.0, -1.0, 1.0, 0.0, 1.5])
        self.declare_parameter("group_name", "manipulator")
        self.declare_parameter("tip_link", "flange")
        self.declare_parameter("enable_on_start", True)
        self.declare_parameter("input_detections_topic", "/yolo/detections")
        self.declare_parameter("input_detections_3d_topic", "/yolo/detections_3d")
        self.declare_parameter("input_camera_info_topic", "/camera/rgb/camera_info")

        rpy = self.get_parameter("grasp_orientation_rpy").value
        wb = self.get_parameter("workspace_bounds").value
        if len(wb) != 6:
            raise ValueError(
                f"workspace_bounds must have exactly 6 values [x_min,x_max,y_min,y_max,z_min,z_max], "
                f"got {len(wb)}: {wb}"
            )
        if wb[0] > wb[1] or wb[2] > wb[3] or wb[4] > wb[5]:
            raise ValueError(f"workspace_bounds has a min > max pair: {wb}")
        workspace_bounds = {
            "x_min": wb[0], "x_max": wb[1],
            "y_min": wb[2], "y_max": wb[3],
            "z_min": wb[4], "z_max": wb[5],
        }

        self._enable_gate = EnableGate(enabled_on_start=self.get_parameter("enable_on_start").value)

        self._latest_camera_info = None
        self._latest_detections_3d = None

        self._status_pub = self.create_publisher(String, "/bridge/status", 10)
        self._publish_status("idle")

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self._pose_converter = PoseConverter(
            score_threshold=self.get_parameter("score_threshold").value,
            base_frame=self.get_parameter("base_frame").value,
            camera_frame=self.get_parameter("camera_frame").value,
            table_height=self.get_parameter("table_height").value,
            grasp_orientation=rpy_to_quaternion(*rpy),
            tf_lookup_fn=self._lookup_transform,
            camera_info_provider=lambda: self._latest_camera_info,
            logger=self.get_logger(),
        )

        cb_group = ReentrantCallbackGroup()
        self._action_client = ActionClient(self, MoveGroup, "/move_action", callback_group=cb_group)
        self._motion_goal_sender = MotionGoalSender(
            action_client=self._action_client,
            group_name=self.get_parameter("group_name").value,
            tip_link=self.get_parameter("tip_link").value,
            workspace_bounds=workspace_bounds,
            status_publisher=self._publish_status,
            logger=self.get_logger(),
        )

        best_effort_qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.BEST_EFFORT)

        self.create_subscription(
            CameraInfo,
            self.get_parameter("input_camera_info_topic").value,
            self._on_camera_info,
            best_effort_qos,
            callback_group=cb_group,
        )
        self.create_subscription(
            DetectionArray,
            self.get_parameter("input_detections_3d_topic").value,
            self._on_detections_3d,
            best_effort_qos,
            callback_group=cb_group,
        )
        self.create_subscription(
            DetectionArray,
            self.get_parameter("input_detections_topic").value,
            self._on_detections,
            best_effort_qos,
            callback_group=cb_group,
        )

        self.create_service(SetBool, "/bridge/enable", self._on_enable_request, callback_group=cb_group)

        self.get_logger().info("bridge_node started")

    def _publish_status(self, status: str) -> None:
        self._status_pub.publish(String(data=status))

    def _lookup_transform(self, target_frame: str, source_frame: str):
        return self._tf_buffer.lookup_transform(target_frame, source_frame, rclpy.time.Time())

    def _on_camera_info(self, msg: CameraInfo) -> None:
        self._latest_camera_info = msg

    def _on_detections_3d(self, msg: DetectionArray) -> None:
        self._latest_detections_3d = msg

    def _on_detections(self, msg: DetectionArray) -> None:
        # US-BR-003 AC1 — disabled pipeline still receives detections, just doesn't act
        if not self._enable_gate.is_enabled():
            return

        pose = self._pose_converter.convert(msg, self._latest_detections_3d)
        if pose is None:
            return  # BR001/BR003 — already logged inside PoseConverter if relevant

        self._motion_goal_sender.send_goal(pose)

    def _on_enable_request(self, request: SetBool.Request, response: SetBool.Response):
        self._enable_gate.set_enabled(request.data)
        response.success = True
        response.message = f"bridge pipeline enabled={request.data}"
        self.get_logger().info(response.message)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BridgeNode()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
