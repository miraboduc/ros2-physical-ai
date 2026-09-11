"""COMP-BR-01 — PoseConverter.

Implements US-BR-001 / BR001-BR003 (docs/design/DDB-bridge-node.md §4).

Dependencies (tf lookup, camera info, clock/logger) are injected as plain
callables so this class can be unit-tested without a running ROS graph
(see test/test_pose_converter.py, mirrors TC-001..TC-004, TC-013 in
docs/testing/QA-testcases.csv).

Scope note (not in the reviewed design doc, added during implementation):
when multiple detections qualify (score >= threshold), this MVP picks the
single highest-scoring one — US-SY-001 only specifies single-object
behavior; multi-object selection is out of scope here.
"""

from geometry_msgs.msg import Point, PoseStamped

from bridge_node.geometry_utils import (
    build_goal_pose,
    pixel_to_camera_ray,
    ray_plane_intersection,
    rotate_vector_by_quaternion,
)


class PoseConverter:
    def __init__(
        self,
        score_threshold: float,
        base_frame: str,
        camera_frame: str,
        table_height: float,
        grasp_orientation,
        tf_lookup_fn,
        camera_info_provider,
        logger,
    ) -> None:
        self.score_threshold = score_threshold
        self.base_frame = base_frame
        self.camera_frame = camera_frame
        self.table_height = table_height
        self.grasp_orientation = grasp_orientation
        # tf_lookup_fn(target_frame, source_frame) -> TransformStamped, raises on failure (BR003)
        self.tf_lookup_fn = tf_lookup_fn
        # camera_info_provider() -> sensor_msgs/CameraInfo or None if not received yet
        self.camera_info_provider = camera_info_provider
        self.logger = logger

    def _pick_best_detection(self, detections_msg):
        """BR001 — filter by score_threshold, pick highest-scoring survivor."""
        candidates = [d for d in detections_msg.detections if d.score >= self.score_threshold]
        if not candidates:
            return None
        return max(candidates, key=lambda d: d.score)

    def _find_matching_3d(self, detection, detections_3d_msg):
        """Best-effort match by class_id — yolo_msgs does not carry a shared
        detection id between /yolo/detections and /yolo/detections_3d.

        Found by code review (2026-09-11): with two objects of the SAME class
        in view (a realistic factory scene — e.g. two identical bins), matching
        by class_id alone can silently pair the picked 2D detection with the
        WRONG instance's 3D pose. There is no way to disambiguate correctly
        without a spatial/IoU correlation (not implemented — see Open Issue #7
        in DDB-bridge-node.md). Safer to refuse the ambiguous match and fall
        back to the 2D+tf2 path (BR003 branch), which stays self-consistent
        because it derives the pose from the SAME bbox that was already picked,
        rather than guessing which 3D detection belongs to it."""
        matches = [d3 for d3 in detections_3d_msg.detections if d3.class_id == detection.class_id]
        if len(matches) > 1:
            self.logger.warning(
                f"PoseConverter: {len(matches)} detections_3d share class_id={detection.class_id}, "
                "ambiguous match — falling back to 2D+tf2 instead of guessing (Open Issue #7)",
                throttle_duration_sec=5.0,
            )
            return None
        return matches[0] if matches else None

    def convert(self, detections_msg, detections_3d_msg=None):
        best = self._pick_best_detection(detections_msg)
        if best is None:
            return None  # BR001 — below threshold, not an error

        if detections_3d_msg is not None:
            best_3d = self._find_matching_3d(best, detections_3d_msg)
            if best_3d is not None:
                # BR002 — use depth-derived pose directly, skip tf2/bbox math
                return build_goal_pose(
                    best_3d.bbox3d.center.position,
                    self.grasp_orientation,
                    self.base_frame,
                    detections_3d_msg.header.stamp,
                )

        camera_info = self.camera_info_provider()
        if camera_info is None:
            self.logger.warning(
                "PoseConverter: no CameraInfo received yet, skipping frame", throttle_duration_sec=5.0
            )
            return None

        # Found by code review (2026-09-11): a CameraInfo message with `k` still at
        # its all-zero default (common right after a camera driver starts, before it
        # publishes real intrinsics) passed the `is None` check above but caused a
        # ZeroDivisionError in pixel_to_camera_ray with no surrounding try/except —
        # unlike the tf2-failure branch below, which degrades gracefully. Treat this
        # the same way: log-throttle and skip the frame instead of crashing.
        if camera_info.k[0] == 0.0 or camera_info.k[4] == 0.0:
            self.logger.warning(
                "PoseConverter: CameraInfo.k has fx/fy == 0 (not calibrated yet?), skipping frame",
                throttle_duration_sec=5.0,
            )
            return None

        try:
            transform = self.tf_lookup_fn(self.base_frame, self.camera_frame)
        except Exception as exc:  # noqa: BLE001 - BR003: any tf2 failure is treated the same
            self.logger.warning(
                f"PoseConverter: tf2 lookup {self.camera_frame}->{self.base_frame} failed ({exc}), "
                "skipping frame",
                throttle_duration_sec=5.0,
            )
            return None

        fx, fy = camera_info.k[0], camera_info.k[4]
        cx, cy = camera_info.k[2], camera_info.k[5]
        u = best.bbox.center.position.x
        v = best.bbox.center.position.y
        ray_cam = pixel_to_camera_ray(u, v, fx, fy, cx, cy)

        rot = transform.transform.rotation
        ray_base_dir = rotate_vector_by_quaternion(ray_cam, rot)
        origin_base = Point(
            x=transform.transform.translation.x,
            y=transform.transform.translation.y,
            z=transform.transform.translation.z,
        )

        point = ray_plane_intersection(origin_base, ray_base_dir, self.table_height)
        if point is None:
            self.logger.warning(
                "PoseConverter: ray does not intersect table_height plane (parallel or behind camera), "
                "skipping frame",
                throttle_duration_sec=5.0,
            )
            return None

        return build_goal_pose(point, self.grasp_orientation, self.base_frame, detections_msg.header.stamp)
