"""Geometry helpers for PoseConverter and MotionGoalSender.

Implements BR001-BR003 (docs/design/DDB-bridge-node.md §4) at the math level:
back-project a 2D bbox center through camera intrinsics into a 3D point on a
known ground plane in base_link, and build a MoveGroup goal_constraints
message from a target PoseStamped (replaces manual IK per DDB-BR-001 §10).
"""

from geometry_msgs.msg import Point, Pose, PoseStamped, Vector3
from moveit_msgs.msg import BoundingVolume, Constraints, OrientationConstraint, PositionConstraint
from shape_msgs.msg import SolidPrimitive


def pixel_to_camera_ray(u: float, v: float, fx: float, fy: float, cx: float, cy: float) -> Vector3:
    """Unnormalized ray direction in the camera optical frame for pixel (u, v)."""
    return Vector3(x=(u - cx) / fx, y=(v - cy) / fy, z=1.0)


def rotate_vector_by_quaternion(v: Vector3, q) -> Vector3:
    """Rotate vector v by quaternion q (geometry_msgs/Quaternion-like, x/y/z/w)."""
    qx, qy, qz, qw = q.x, q.y, q.z, q.w
    vx, vy, vz = v.x, v.y, v.z
    # v' = v + 2*qw*(q_xyz x v) + 2*(q_xyz x (q_xyz x v))
    cross1_x = qy * vz - qz * vy
    cross1_y = qz * vx - qx * vz
    cross1_z = qx * vy - qy * vx
    cross2_x = qy * cross1_z - qz * cross1_y
    cross2_y = qz * cross1_x - qx * cross1_z
    cross2_z = qx * cross1_y - qy * cross1_x
    return Vector3(
        x=vx + 2 * qw * cross1_x + 2 * cross2_x,
        y=vy + 2 * qw * cross1_y + 2 * cross2_y,
        z=vz + 2 * qw * cross1_z + 2 * cross2_z,
    )


def ray_plane_intersection(
    origin: Point, direction: Vector3, plane_z: float
) -> Point | None:
    """Intersect a ray (already expressed in the plane's frame, e.g. base_link)
    with the horizontal plane z = plane_z. Returns None if the ray is parallel
    to the plane (direction.z ~ 0) or the intersection is behind the origin (t < 0)."""
    if abs(direction.z) < 1e-9:
        return None
    t = (plane_z - origin.z) / direction.z
    if t < 0:
        return None
    return Point(x=origin.x + t * direction.x, y=origin.y + t * direction.y, z=plane_z)


def build_goal_pose(position: Point, grasp_orientation, frame_id: str, stamp) -> PoseStamped:
    """Assemble a PoseStamped from a computed 3D point and a configured
    approach orientation. See Open Issue "grasp_orientation" in
    DDB-bridge-node.md — the orientation is a configured parameter, not
    derived from the detection (2D bbox carries no orientation information)."""
    ps = PoseStamped()
    ps.header.frame_id = frame_id
    ps.header.stamp = stamp
    ps.pose = Pose(position=position, orientation=grasp_orientation)
    return ps


def pose_to_goal_constraints(
    pose_stamped: PoseStamped,
    link_name: str,
    position_tolerance: float = 0.01,
    orientation_tolerance: float = 0.05,
) -> Constraints:
    """Build a moveit_msgs/Constraints for a single-pose goal, equivalent to
    MoveIt's kinematic_constraints::constructGoalConstraints (C++), so that
    MoveGroup performs IK + collision-aware planning itself (DDB-BR-001 §10,
    Open Issue #2 — closed 2026-09-11)."""
    constraints = Constraints()

    pc = PositionConstraint()
    pc.header = pose_stamped.header
    pc.link_name = link_name
    sphere = SolidPrimitive(type=SolidPrimitive.SPHERE, dimensions=[position_tolerance])
    bv = BoundingVolume(primitives=[sphere], primitive_poses=[pose_stamped.pose])
    pc.constraint_region = bv
    pc.weight = 1.0
    constraints.position_constraints.append(pc)

    oc = OrientationConstraint()
    oc.header = pose_stamped.header
    oc.link_name = link_name
    oc.orientation = pose_stamped.pose.orientation
    oc.absolute_x_axis_tolerance = orientation_tolerance
    oc.absolute_y_axis_tolerance = orientation_tolerance
    oc.absolute_z_axis_tolerance = orientation_tolerance
    oc.weight = 1.0
    constraints.orientation_constraints.append(oc)

    return constraints
