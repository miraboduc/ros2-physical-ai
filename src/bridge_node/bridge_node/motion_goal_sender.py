"""COMP-BR-02 — MotionGoalSender.

Implements US-BR-002 / BR004-BR005 (docs/design/DDB-bridge-node.md §4, §6.4).
Sends a moveit_msgs/action/MoveGroup goal to the external `move_group` node
(EXT-MO-01, action name `/move_action` — verified 2026-09-11 against
`fanuc_moveit_config` mock hardware) instead of computing IK itself.

`action_client` is injected so this class is unit-testable without a real
action server (see test/test_motion_goal_sender.py, mirrors TC-005..TC-007
in docs/testing/QA-testcases.csv) — it only needs to expose
`send_goal_async(goal) -> Future[goal_handle]` where
`goal_handle.accepted: bool` and `goal_handle.get_result_async() -> Future[result]`.
"""

import threading

from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import MoveItErrorCodes, PlanningOptions

from bridge_node.geometry_utils import pose_to_goal_constraints


class MotionGoalSender:
    def __init__(
        self,
        action_client,
        group_name: str,
        tip_link: str,
        workspace_bounds: dict,
        status_publisher,
        logger,
    ) -> None:
        self.action_client = action_client
        self.group_name = group_name
        self.tip_link = tip_link
        self.workspace_bounds = workspace_bounds
        self.status_publisher = status_publisher
        self.logger = logger
        self._busy = False
        # Found by code review (2026-09-11, pre-delivery gate) before the real-robot
        # trial: `bridge_node.py` puts the detection subscriptions AND the action
        # client on the same ReentrantCallbackGroup under MultiThreadedExecutor, so
        # two detection callbacks can run concurrently. A plain bool `_busy` has a
        # check-then-act race — two threads can both observe `_busy is False` before
        # either sets it True, both pass the workspace/server checks, and both send a
        # goal to the real robot. This lock makes "check busy, check preconditions,
        # set busy, send" one atomic unit — the actual fix for BR008, not just the
        # single-threaded version of it.
        #
        # RLock, not Lock: in real rclpy the goal-response/result callbacks fire
        # later, outside this call's lock scope, so a plain Lock would be fine —
        # but this package's OWN test doubles call add_done_callback's callback
        # immediately (synchronously) instead of deferring it, so a plain Lock
        # self-deadlocked the moment a test exercised this path (same thread
        # re-entering `with self._lock` from inside `_on_goal_response`/`_on_result`,
        # still nested inside `send_goal`'s own `with` block). RLock costs nothing
        # here and removes that whole class of risk.
        self._lock = threading.RLock()

    def is_busy(self) -> bool:
        """True from the moment a goal is accepted until its result resolves
        (State Dynamics View §3: EXECUTING doesn't accept a new goal). Found
        missing while preparing to run vision+motion concurrently — with a
        single detection per test this never mattered, but a continuous
        detection stream would otherwise fire overlapping MoveGroup goals
        while one is still executing."""
        return self._busy

    def is_in_workspace(self, point) -> bool:
        b = self.workspace_bounds
        return (
            b["x_min"] <= point.x <= b["x_max"]
            and b["y_min"] <= point.y <= b["y_max"]
            and b["z_min"] <= point.z <= b["z_max"]
        )

    def send_goal(self, pose_stamped) -> None:
        with self._lock:
            if self._busy:
                self.logger.debug("MotionGoalSender: already executing a goal, ignoring new detection")
                return

            if not self.is_in_workspace(pose_stamped.pose.position):
                p = pose_stamped.pose.position
                self.logger.warning(
                    f"MotionGoalSender: pose ({p.x:.3f}, {p.y:.3f}, {p.z:.3f}) outside "
                    f"workspace_bounds {self.workspace_bounds} — goal rejected, not sent (BR004)"
                )
                return

            # Found via integration test (TC-008, 2026-09-11): send_goal_async() on a dead/
            # unavailable action server never resolves — no accepted/rejected callback ever
            # fires, no exception, node hangs in "executing" forever. server_is_ready() is a
            # cheap, non-blocking check that catches the common case (server never came up,
            # or already died). It does NOT catch the rarer race where the server dies
            # between this check and the actual send — that's a known, accepted gap for MVP.
            if not self.action_client.server_is_ready():
                self.logger.error("MotionGoalSender: /move_action server not available, goal not sent")
                self.status_publisher("error")
                return

            goal = MoveGroup.Goal()
            goal.request.group_name = self.group_name
            goal.request.goal_constraints = [pose_to_goal_constraints(pose_stamped, self.tip_link)]
            goal.request.num_planning_attempts = 5
            goal.request.allowed_planning_time = 5.0
            goal.request.max_velocity_scaling_factor = 0.5
            goal.request.max_acceleration_scaling_factor = 0.5
            goal.planning_options = PlanningOptions(plan_only=False)

            self._busy = True
            self.status_publisher("executing")
            send_future = self.action_client.send_goal_async(goal)
            send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            with self._lock:
                self._busy = False
            self.logger.error("MotionGoalSender: goal rejected by move_group action server")
            self.status_publisher("error")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_result(self, future) -> None:
        with self._lock:
            self._busy = False
        result = future.result().result
        if result.error_code.val == MoveItErrorCodes.SUCCESS:
            self.status_publisher("reached")
        else:
            # BR005 — log and stop; do NOT automatically resend this goal
            self.logger.error(
                f"MotionGoalSender: goal did not succeed, error_code={result.error_code.val} "
                "(no automatic retry, per BR005)"
            )
            self.status_publisher("error")
