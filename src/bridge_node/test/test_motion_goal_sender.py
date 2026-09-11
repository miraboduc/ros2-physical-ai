"""Unit tests for MotionGoalSender (COMP-BR-02) — mirrors TC-005..TC-007
in docs/testing/QA-testcases.csv. The action client is a fake whose futures
resolve synchronously, so no rclpy executor/spin is needed."""

import threading
import time

from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion
from moveit_msgs.msg import MoveItErrorCodes

from bridge_node.motion_goal_sender import MotionGoalSender

WORKSPACE = {"x_min": -1.0, "x_max": 1.0, "y_min": -1.0, "y_max": 1.0, "z_min": 0.0, "z_max": 1.5}


class FakeFuture:
    def __init__(self, result_value):
        self._result_value = result_value

    def result(self):
        return self._result_value

    def add_done_callback(self, cb):
        cb(self)


class FakeErrorCode:
    def __init__(self, val):
        self.val = val


class FakeResult:
    def __init__(self, error_code_val):
        self.error_code = FakeErrorCode(error_code_val)


class FakeGoalResult:
    def __init__(self, error_code_val):
        self.result = FakeResult(error_code_val)


class FakeGoalHandle:
    def __init__(self, accepted, error_code_val=MoveItErrorCodes.SUCCESS):
        self.accepted = accepted
        self._error_code_val = error_code_val

    def get_result_async(self):
        return FakeFuture(FakeGoalResult(self._error_code_val))


class FakeActionClient:
    def __init__(self, goal_handle, server_ready=True):
        self.goal_handle = goal_handle
        self.sent_goals = []
        self._server_ready = server_ready

    def server_is_ready(self):
        return self._server_ready

    def send_goal_async(self, goal):
        self.sent_goals.append(goal)
        return FakeFuture(self.goal_handle)


class FakeLogger:
    def __init__(self):
        self.warnings, self.errors = [], []

    def warning(self, msg, **kwargs):
        self.warnings.append(msg)

    def error(self, msg, **kwargs):
        self.errors.append(msg)

    def info(self, msg, **kwargs):
        pass

    def debug(self, msg, **kwargs):
        pass


def make_pose(x, y, z):
    return PoseStamped(pose=Pose(position=Point(x=x, y=y, z=z), orientation=Quaternion(w=1.0)))


def make_sender(goal_handle):
    action_client = FakeActionClient(goal_handle)
    logger = FakeLogger()
    statuses = []
    sender = MotionGoalSender(
        action_client=action_client,
        group_name="manipulator",
        tip_link="flange",
        workspace_bounds=WORKSPACE,
        status_publisher=statuses.append,
        logger=logger,
    )
    return sender, action_client, logger, statuses


def test_tc005_happy_path_sends_goal_and_reports_reached():
    sender, action_client, logger, statuses = make_sender(
        FakeGoalHandle(accepted=True, error_code_val=MoveItErrorCodes.SUCCESS)
    )

    sender.send_goal(make_pose(0.5, 0.0, 0.5))

    assert len(action_client.sent_goals) == 1
    assert statuses == ["executing", "reached"]
    assert logger.errors == []


def test_tc006_outside_workspace_rejected_before_sending():
    sender, action_client, logger, statuses = make_sender(FakeGoalHandle(accepted=True))

    sender.send_goal(make_pose(5.0, 0.0, 0.5))  # x=5.0 is outside x_max=1.0

    assert action_client.sent_goals == []  # BR004 — never sent to the action server
    assert statuses == []  # status must not switch to "executing"
    assert len(logger.warnings) == 1


def test_tc007_aborted_result_reports_error_and_does_not_retry():
    sender, action_client, logger, statuses = make_sender(
        FakeGoalHandle(accepted=True, error_code_val=MoveItErrorCodes.PLANNING_FAILED)
    )

    sender.send_goal(make_pose(0.5, 0.0, 0.5))

    assert len(action_client.sent_goals) == 1  # sent exactly once — BR005, no auto-retry
    assert statuses == ["executing", "error"]
    assert len(logger.errors) == 1


class PendingFuture:
    """A future that never resolves — simulates a goal still in flight."""

    def add_done_callback(self, cb):
        pass  # intentionally never invoked


class BusyActionClient(FakeActionClient):
    def send_goal_async(self, goal):
        self.sent_goals.append(goal)
        return PendingFuture()


def test_ignores_new_detection_while_a_goal_is_still_executing():
    """Found missing while preparing to run vision+motion concurrently: with
    only one detection per test, this gap never showed up before."""
    action_client = BusyActionClient(FakeGoalHandle(accepted=True))
    logger = FakeLogger()
    statuses = []
    sender = MotionGoalSender(
        action_client=action_client,
        group_name="manipulator",
        tip_link="flange",
        workspace_bounds=WORKSPACE,
        status_publisher=statuses.append,
        logger=logger,
    )

    sender.send_goal(make_pose(0.5, 0.0, 0.5))  # first goal — never resolves, stays "busy"
    assert sender.is_busy() is True

    sender.send_goal(make_pose(0.6, 0.0, 0.5))  # second detection arrives mid-flight

    assert len(action_client.sent_goals) == 1  # second one must be ignored, not sent
    assert statuses == ["executing"]  # only one "executing", no duplicate


class SlowServerCheckActionClient(FakeActionClient):
    """server_is_ready() sleeps briefly to deliberately widen the check-then-act
    race window that BLOCKER B1 (code review, 2026-09-11) found: two threads
    could both observe `_busy is False`, both pass this check, and both send."""

    def server_is_ready(self):
        time.sleep(0.02)
        return self._server_ready

    def send_goal_async(self, goal):
        # Deliberately never resolves — a real in-flight MoveGroup goal stays
        # pending for seconds, so `_busy` must stay True for this whole test.
        # (An earlier version of this test used FakeFuture, whose
        # add_done_callback resolves synchronously — that made every thread's
        # goal complete instantly inside its own turn, so the lock's mutual
        # exclusion was real but there was never an actual "goal still in
        # flight" for a later thread to collide with. That version passed for
        # the wrong reason and would not have caught B1.)
        self.sent_goals.append(goal)
        return PendingFuture()


def test_concurrent_detections_never_send_overlapping_goals():
    """Regression test for the race condition found in code review (BLOCKER B1,
    2026-09-11): bridge_node.py puts detection callbacks and the action client on
    the same ReentrantCallbackGroup, so send_goal() can genuinely be entered by
    multiple threads at once when a fast detection stream overlaps a slow
    server_is_ready() check. Without the lock in MotionGoalSender, this test
    reliably sent 2+ goals; with it, exactly one must win."""
    action_client = SlowServerCheckActionClient(FakeGoalHandle(accepted=True))
    logger = FakeLogger()
    statuses = []
    sender = MotionGoalSender(
        action_client=action_client,
        group_name="manipulator",
        tip_link="flange",
        workspace_bounds=WORKSPACE,
        status_publisher=statuses.append,
        logger=logger,
    )

    threads = [threading.Thread(target=sender.send_goal, args=(make_pose(0.5, 0.0, 0.5),)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(action_client.sent_goals) == 1


def test_tc008_action_server_unavailable_reports_error_immediately():
    action_client = FakeActionClient(FakeGoalHandle(accepted=True), server_ready=False)
    logger = FakeLogger()
    statuses = []
    sender = MotionGoalSender(
        action_client=action_client,
        group_name="manipulator",
        tip_link="flange",
        workspace_bounds=WORKSPACE,
        status_publisher=statuses.append,
        logger=logger,
    )

    sender.send_goal(make_pose(0.5, 0.0, 0.5))

    assert action_client.sent_goals == []  # never attempted — would hang forever otherwise
    assert statuses == ["error"]
    assert len(logger.errors) == 1
