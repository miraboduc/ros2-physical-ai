"""Unit tests for PoseConverter (COMP-BR-01) — mirrors TC-001..TC-004, TC-013
in docs/testing/QA-testcases.csv. No ROS node/executor needed — tf lookup and
camera info are injected fakes."""

import math

import pytest
from geometry_msgs.msg import Quaternion, Transform, TransformStamped, Vector3
from sensor_msgs.msg import CameraInfo
from yolo_msgs.msg import BoundingBox2D, BoundingBox3D, Detection, DetectionArray, Point2D, Pose2D

from bridge_node.pose_converter import PoseConverter

IDENTITY_QUAT = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, msg, **kwargs):
        self.warnings.append(msg)

    def error(self, msg, **kwargs):
        self.errors.append(msg)

    def info(self, msg, **kwargs):
        pass


def make_detection(score, u=50.0, v=50.0, class_id=0):
    d = Detection()
    d.class_id = class_id
    d.score = score
    d.bbox = BoundingBox2D(center=Pose2D(position=Point2D(x=u, y=v)))
    return d


def make_camera_info(fx=100.0, fy=100.0, cx=50.0, cy=50.0):
    info = CameraInfo()
    info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
    return info


def identity_transform():
    ts = TransformStamped()
    ts.transform = Transform(translation=Vector3(x=0.0, y=0.0, z=0.0), rotation=IDENTITY_QUAT)
    return ts


def make_converter(tf_lookup_fn=None, camera_info=None, table_height=2.0, score_threshold=0.5):
    logger = FakeLogger()
    converter = PoseConverter(
        score_threshold=score_threshold,
        base_frame="base_link",
        camera_frame="camera_link",
        table_height=table_height,
        grasp_orientation=IDENTITY_QUAT,
        tf_lookup_fn=tf_lookup_fn or (lambda *_: identity_transform()),
        camera_info_provider=lambda: camera_info,
        logger=logger,
    )
    return converter, logger


def test_tc001_below_threshold_is_ignored():
    converter, logger = make_converter(camera_info=make_camera_info())
    msg = DetectionArray(detections=[make_detection(score=0.3)])

    result = converter.convert(msg)

    assert result is None
    assert logger.warnings == []  # BR001: not an error, no log


def test_tc013_score_exactly_at_threshold_is_included():
    converter, logger = make_converter(camera_info=make_camera_info(), score_threshold=0.5)
    msg = DetectionArray(detections=[make_detection(score=0.5, u=50.0, v=50.0)])

    result = converter.convert(msg)

    assert result is not None  # score == threshold must NOT be filtered out


def test_tc002_happy_path_computes_pose_via_tf2():
    converter, logger = make_converter(camera_info=make_camera_info(fx=100, fy=100, cx=50, cy=50), table_height=2.0)
    msg = DetectionArray(detections=[make_detection(score=0.8, u=50.0, v=50.0)])

    result = converter.convert(msg)

    assert result is not None
    assert result.header.frame_id == "base_link"
    # pixel at principal point -> ray (0,0,1) -> identity transform -> hits z=2.0 plane at (0,0,2.0)
    assert math.isclose(result.pose.position.x, 0.0, abs_tol=1e-9)
    assert math.isclose(result.pose.position.y, 0.0, abs_tol=1e-9)
    assert math.isclose(result.pose.position.z, 2.0, abs_tol=1e-9)


def test_tc003_uses_detections_3d_directly_without_tf_lookup():
    tf_calls = []

    def tracking_tf_lookup(target, source):
        tf_calls.append((target, source))
        return identity_transform()

    converter, logger = make_converter(tf_lookup_fn=tracking_tf_lookup, camera_info=make_camera_info())
    detections_2d = DetectionArray(detections=[make_detection(score=0.8, class_id=3)])
    d3 = Detection(class_id=3)
    d3.bbox3d = BoundingBox3D()
    d3.bbox3d.center.position.x = 1.0
    d3.bbox3d.center.position.y = 2.0
    d3.bbox3d.center.position.z = 3.0
    detections_3d = DetectionArray(detections=[d3])

    result = converter.convert(detections_2d, detections_3d)

    assert result is not None
    assert (result.pose.position.x, result.pose.position.y, result.pose.position.z) == (1.0, 2.0, 3.0)
    assert tf_calls == []  # BR002: must NOT call tf2 when detections_3d already has the pose


def test_tc004_tf2_lookup_failure_skips_frame_without_crashing():
    def failing_tf_lookup(target, source):
        raise RuntimeError("transform not available")

    converter, logger = make_converter(tf_lookup_fn=failing_tf_lookup, camera_info=make_camera_info())
    msg = DetectionArray(detections=[make_detection(score=0.8)])

    result = converter.convert(msg)  # must not raise

    assert result is None
    assert len(logger.warnings) == 1
    assert "tf2 lookup" in logger.warnings[0]


def test_zero_fx_fy_camera_info_skips_frame_without_crashing():
    """Regression test for MAJOR M1 (code review, 2026-09-11): a CameraInfo
    with the all-zero default `k` (real startup timing glitch, camera driver
    hasn't published real intrinsics yet) must degrade like a tf2 failure,
    not raise ZeroDivisionError from pixel_to_camera_ray."""
    converter, logger = make_converter(camera_info=make_camera_info(fx=0.0, fy=0.0))
    msg = DetectionArray(detections=[make_detection(score=0.8)])

    result = converter.convert(msg)  # must not raise

    assert result is None
    assert any("fx/fy == 0" in w for w in logger.warnings)


def test_ambiguous_detections_3d_falls_back_to_2d_instead_of_guessing():
    """Regression test for MAJOR M2 (code review, 2026-09-11): two objects of
    the same class in /yolo/detections_3d must not be silently paired with
    the wrong instance — fall back to the 2D+tf2 path instead."""
    converter, logger = make_converter(camera_info=make_camera_info(), table_height=2.0)
    detections_2d = DetectionArray(detections=[make_detection(score=0.8, u=50.0, v=50.0, class_id=3)])

    d3_a = Detection(class_id=3)
    d3_a.bbox3d.center.position.x = 1.0
    d3_b = Detection(class_id=3)
    d3_b.bbox3d.center.position.x = 99.0  # a very different, wrong instance
    detections_3d = DetectionArray(detections=[d3_a, d3_b])

    result = converter.convert(detections_2d, detections_3d)

    assert result is not None
    # fell back to 2D+tf2 (pixel at principal point -> x=0.0), NOT either 3D candidate
    assert result.pose.position.x not in (1.0, 99.0)
    assert any("ambiguous match" in w for w in logger.warnings)


def test_no_camera_info_yet_skips_frame():
    converter, logger = make_converter(camera_info=None)
    msg = DetectionArray(detections=[make_detection(score=0.8)])

    result = converter.convert(msg)

    assert result is None
    assert any("CameraInfo" in w for w in logger.warnings)
