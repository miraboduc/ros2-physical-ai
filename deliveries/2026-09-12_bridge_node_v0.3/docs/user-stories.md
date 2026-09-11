---
type: User Stories
title: Vision → Motion Bridge cho ROS2 Physical AI (Fanuc)
project: ros2-physical-ai
created_by: Hoang Duc
created_at: 2026-09-11
source_docs: [ROADMAP.md, docs/../../.claude/projects/.../memory/fanuc_driver_vision_gap.md, docs/../../.claude/projects/.../memory/env_deviation_from_roadmap.md]
status: draft
---

# User Stories — Vision → Motion Bridge (ROS2 + Fanuc)

**Ngôn ngữ**: Tiếng Việt
**Nguồn yêu cầu**: [ROADMAP.md](../../ROADMAP.md) (đóng vai trò High-Level Design, Phase 0-5) + xác nhận kỹ thuật thực tế 2026-09-11 (yolo_ros build/run thành công, fanuc_driver clone về, không có sample vision+motion kết hợp — xem memory `fanuc_driver_vision_gap`).

**Phạm vi**: Các story dưới đây mô tả toàn bộ pipeline "camera thấy vật thể → tay máy Fanuc di chuyển tới vật thể đó" chạy trên ROS2. Một phần capability (Vision, Motion) đã có sẵn qua package tái sử dụng (yolo_ros, fanuc_driver) — được ghi lại đầy đủ ở đây để traceability, dù không cần code mới. Phần **Bridge (module BR)** là code mới duy nhất cần viết.

**CMMI Traceability**: Dự án chưa có `PLN-reqanalysis.md`/`SPC-srs.md` chính thức — ROADMAP.md đóng vai trò tài liệu yêu cầu cấp cao tạm thời. Trường StRS/REQ IDs để trống, dùng cột "Nguồn" (tham chiếu Phase trong ROADMAP.md) thay thế cho tới khi có SRS chính thức.

---

## Module ID

| Module | ID | Mô tả |
|---|---|---|
| Vision | `V` | Node nhận diện object từ camera (yolo_ros — reuse) |
| Bridge | `BR` | Node cầu nối vision → motion (code mới, chưa tồn tại) |
| Motion | `MO` | Điều khiển chuyển động tay máy Fanuc (fanuc_driver — reuse) |
| System | `SY` | Story tích hợp end-to-end, góc nhìn Operator |

**Quy ước Platform** (đổi ý nghĩa so với template gốc — dự án robot không có Web/iOS/Android):
`Simulation (Gazebo)` | `Real Robot (Fanuc)` | `Both`

---

## US-V-001: Publish object detections from camera image

- **As a** Vision Node
- **I want to** publish detected object bounding boxes from an RGB camera image
- **So that** downstream nodes can act on real-time detection results

**Acceptance Criteria**:
- ✅ Khi có ảnh mới trên topic camera (`input_image_topic`), node publish message chứa danh sách object lên `/yolo/detections` (class_id, class_name, score, bbox 2D center+size)
- ✅ Nếu không object nào vượt ngưỡng `threshold`, message detections publish rỗng (không lỗi, không crash)
- ✅ Node chạy inference trên GPU theo tham số `device` (mặc định `cuda:0`), không rơi về CPU âm thầm

> **Ghi chú kỹ thuật (không tính AC chính thức — trigger khác, xem review F-Q5-01)**: Node cũng có service `/yolo/enable` để bật/tắt mà không cần restart process. Đây là capability sẵn có của package, không thuộc phạm vi AC của story này.

**Dependencies**: None
**Related**: US-BR-001
**Blocks**: US-BR-001
**Platform**: Both (code không đổi giữa Simulation/Real Robot, chỉ đổi `input_image_topic`)
**Estimation**: 0 SP mới — **Done** (reuse [mgonzs13/yolo_ros](https://github.com/mgonzs13/yolo_ros), không viết code)
**Nguồn**: ROADMAP.md Phase 3

**Status**: ✅ Done — verified 2026-09-11 (demo end-to-end với ảnh test, phát hiện đúng "bus" 94.6%, "person" 90.3%, chạy trên RTX 3070 qua CUDA, 420MB VRAM)
**Sprint**: —
**Assignee**: —
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## US-BR-001: Convert 2D detection into 3D target pose

- **As a** Bridge Node
- **I want to** convert a 2D detection bounding box into a 3D target pose in the robot base frame
- **So that** the motion layer receives a pose it can plan a trajectory to

**Acceptance Criteria**:
- ✅ Khi nhận message mới từ `/yolo/detections` có ít nhất 1 object với `score` ≥ ngưỡng cấu hình, node tính pose 3D bằng camera calibration + tf2 lookup (`camera_frame` → `robot_base_frame`)
- ✅ Nếu topic `/yolo/detections_3d` có sẵn (camera depth), dùng trực tiếp pose 3D đó, không tự tính lại từ bbox 2D
- ✅ Nếu object có `score` dưới ngưỡng, bỏ qua object đó trong frame hiện tại (không tính pose, không log lỗi — đây là hành vi bình thường)
- ✅ Nếu tf2 lookup thất bại (transform chưa sẵn sàng), log warning throttle (không spam log) và bỏ qua frame đó, node không crash

**Dependencies**: US-V-001
**Related**: US-BR-002
**Blocks**: US-BR-002, US-SY-001
**Platform**: Both (logic giống nhau; khác camera intrinsics/tf tree thật giữa Gazebo và Fanuc thật)
**Estimation**: 5 SP (camera calibration + tf2 handling + xử lý depth-vs-2D)
**Nguồn**: ROADMAP.md Phase 3-4

**Status**: ✅ Done — implemented (`bridge_node` package, `PoseConverter`), 5 unit test pass + verified qua integration test end-to-end (TC-002/003/004/013). Open Issue #5/#6 (table_height, grasp_orientation — xem DDB-bridge-node.md) là giá trị placeholder chưa đo thật, không chặn việc coi AC đã pass.
**Sprint**: —
**Assignee**: Hoang Duc
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## US-BR-002: Send motion goal to Fanuc arm for detected object pose

- **As a** Bridge Node
- **I want to** send a motion goal to the Fanuc arm for the computed 3D target pose
- **So that** the robot moves toward the detected object

**Acceptance Criteria**:
- ✅ Khi có pose 3D hợp lệ mới từ US-BR-001, node gửi goal qua action `FollowJointTrajectory` (hoặc MoveGroup của `fanuc_moveit_config`) tới `fanuc_driver`
- ✅ Nếu pose nằm ngoài workspace/reach của robot (kiểm tra trước khi gửi), node từ chối gửi goal và log rõ lý do — không gửi lệnh nguy hiểm cho action server
- ✅ Khi action server trả kết quả SUCCESS, node publish trạng thái pipeline "đã tới đích" lên topic riêng để giám sát
- ✅ Khi action server trả ABORTED/lỗi, node log lỗi và giữ nguyên trạng thái an toàn hiện tại — không tự động retry vô hạn

**Dependencies**: US-BR-001, US-MO-001
**Related**: US-BR-001
**Blocks**: US-SY-001
**Platform**: Both (đổi action server name/namespace khi chuyển Gazebo ↔ Fanuc thật, logic gọi action giống nhau)
**Estimation**: 5 SP
**Nguồn**: ROADMAP.md Phase 4 (bước 1-3: pipeline/lookahead, shared latest-detection state)

**Status**: ✅ Done — implemented (`MotionGoalSender`, dùng `MoveGroup` action thay `FollowJointTrajectory` trực tiếp — xem DDB-bridge-node.md §10), 4 unit test pass + verified integration test thật trên `fanuc_moveit_config` mock hardware (TC-005 happy path SUCCESS, TC-006 reject ngoài workspace, TC-007 ABORTED/PLANNING_FAILED không retry). Phát hiện + fix 1 bug thật (BR007 — action server chết làm node hang vô hạn, TC-008).
**Sprint**: —
**Assignee**: Hoang Duc
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## US-BR-003: Set pipeline enabled state

- **As a** Robot Operator
- **I want to** set whether the detection-to-motion pipeline is enabled
- **So that** I can safely pause automatic robot movement during setup or debugging

**Acceptance Criteria**:
- ✅ Gọi service `/bridge/enable` với giá trị `False` → node ngừng gửi goal mới tới tay máy (vẫn nhận detection, chỉ không hành động)
- ✅ Gọi service `/bridge/enable` với giá trị `True` → node tiếp tục pipeline bình thường ngay từ detection kế tiếp
- ✅ Khi disable được gọi trong lúc tay máy đang thực thi 1 trajectory đã gửi trước đó, tay máy **hoàn thành trajectory hiện tại** (không dừng đột ngột giữa đường), sau đó không nhận goal mới cho tới khi enable lại
- ℹ️ *(Cấu hình khởi tạo, trigger khác — xem review F-Q5-02)* Khi node khởi động lần đầu, pipeline ở trạng thái `enable=True` theo tham số launch mặc định (có thể override qua launch argument)

**Dependencies**: US-BR-002
**Related**: US-V-001 (yolo_ros đã có `/yolo/enable` cùng pattern)
**Blocks**: None
**Platform**: Both
**Estimation**: 3 SP (tăng từ 2 SP sau review — thêm xử lý an toàn khi disable giữa lúc đang di chuyển)
**Nguồn**: ROADMAP.md — nguyên tắc an toàn vận hành (không có Phase cụ thể, suy ra từ thực hành chuẩn robotics)

**Status**: ✅ Done — implemented (`EnableGate`), 4 unit test pass + verified integration test thật (TC-009 disable chặn goal mới, TC-010 enable lại resume, TC-011 disable giữa lúc EXECUTING không cắt trajectory hiện tại — đúng BR006).
**Sprint**: —
**Assignee**: Hoang Duc
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## US-MO-001: Execute joint trajectory received from action client

- **As a** Fanuc Robot Arm
- **I want to** execute a joint trajectory received via the FollowJointTrajectory action
- **So that** it physically reaches the pose requested by the bridge node

**Acceptance Criteria**:
- ✅ Khi nhận goal hợp lệ (trong giới hạn khớp/vận tốc, không va chạm theo MoveIt2 planning scene), tay máy di chuyển theo trajectory và trả action result SUCCESS khi hoàn tất
- ✅ Khi goal vượt giới hạn khớp hoặc phát hiện va chạm, tay máy từ chối/abort goal — không thực hiện chuyển động nguy hiểm
- ✅ Trạng thái khớp hiện tại luôn publish liên tục trên `/joint_states` để bridge node/hệ thống giám sát theo dõi được real-time

**Dependencies**: None (capability có sẵn từ `fanuc_driver` + `ros2_control`, không code mới)
**Related**: US-BR-002
**Blocks**: US-BR-002 (bridge cần action server này tồn tại và chạy để gửi goal)
**Platform**: Simulation (qua `ros2_control` hardware_interface mô phỏng trên Gazebo Harmonic) & Real Robot (qua `fanuc_driver` streaming driver thật — cần xác nhận model CRX + software option theo ROADMAP Phase 5, chưa chốt)
**Estimation**: 0 SP code mới (100% reuse `fanuc_driver`) — nhưng cần 2 SP công việc tích hợp/verify (build + test trên Gazebo) trước khi coi là xong; cấu hình URDF/controller cho robot cụ thể thật (Phase 5) chưa ước lượng ở đây
**Nguồn**: ROADMAP.md Phase 2 (ros2_control abstraction), Phase 5 (Fanuc thật — điều kiện CRX + S636 option chưa xác nhận)

**Status**: ✅ Done — build thành công, `joint_trajectory_controller` + `move_group` activate và chạy được, `/joint_states` publish đúng (J1-J6, `base_link`). AC1 verify thật qua Bridge Node integration test (goal SUCCESS, robot thực sự di chuyển qua mock hardware). AC2 verify qua TC-007 (pose ngoài tầm với → PLANNING_FAILED, không di chuyển nguy hiểm). AC3 (`/joint_states` liên tục) verify qua `ros2 topic echo`.
**Sprint**: —
**Assignee**: —
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## US-SY-001: Detect and reach a single object in camera view (end-to-end)

- **As a** Robot Operator
- **I want to** see the robot arm move toward a single detected object automatically
- **So that** I can validate the end-to-end perception-to-motion pipeline before adding pick/place logic

**Acceptance Criteria**:
- ✅ Khi camera nhìn thấy đúng 1 object đã train, tay máy tự động di chuyển đầu công cụ (tool0) tới gần pose object đó — thời gian đo thực tế trên simulator, không giả định số liệu ROADMAP (mục tiêu tham khảo: giảm chu kỳ 2-3s so với baseline tuần tự, đo lại ở Phase 4 khi có baseline)
- ✅ Khi không có object nào trong tầm nhìn, tay máy giữ nguyên vị trí home — không di chuyển ngẫu nhiên hoặc lặp lại lệnh cũ
- ✅ Khi object di chuyển ra khỏi tầm nhìn giữa lúc tay máy đang chạy tới, tay máy hoàn thành trajectory hiện tại rồi mới đứng yên (không đổi hướng giữa đường) — xử lý vật thể di động/băng chuyền là **ngoài phạm vi** story này, thuộc ROADMAP Phase 4 bước 4 (Kalman filter/extrapolate), sẽ là story riêng sau

**Dependencies**: US-BR-001, US-BR-002, US-MO-001
**Related**: US-BR-003
**Blocks**: None
**Platform**: Simulation (Gazebo) trước — Real Robot sau khi Phase 5 xác nhận model/option
**Estimation**: — (story tích hợp/xác nhận, không cộng SP riêng ngoài US-BR-001 + US-BR-002 + US-MO-001)
**Nguồn**: ROADMAP.md Phase 4 (mục tiêu cuối), Phần "Cách làm việc cùng nhau" (không chuyển phase nếu chưa đo thật)

**Status**: ✅ Done — verify thật 2026-09-11 với `yolo_ros` + camera stream (3Hz, ảnh test) chạy **song song thật** với `bridge_node` + `fanuc_moveit_config` mock hardware. Xác nhận: object trong tầm nhìn → tay máy di chuyển; vision không hề bị chặn/gián đoạn trong lúc tay máy di chuyển (giữ nguyên 3Hz suốt); không có goal chồng lấp (fix BR008, phát hiện đúng lúc chuẩn bị test này). Còn lại: `table_height`/`grasp_orientation` (Open Issue #5/#6) là placeholder nên pose tính ra không phải lúc nào cũng physically hợp lệ — không phải bug, cần đo thật trước khi có ý nghĩa với vật thể/robot thật.
**Sprint**: —
**Assignee**: —
**Created**: 2026-09-11 | **Updated**: 2026-09-11

---

## Ma trận Dependencies (thứ tự triển khai)

```
US-V-001 (Done) ──┐
                   ├──► US-BR-001 ──► US-BR-002 ──► US-SY-001
US-MO-001 (build) ─┘                     │
                                          └──► US-BR-003 (enable/disable, có thể làm song song sau BR-002)
```

**Đường găng (critical path) để có demo end-to-end trên Gazebo**: US-MO-001 (build fanuc_driver trên Gazebo) song song với US-BR-001 → US-BR-002 → US-SY-001. US-BR-003 không nằm trên đường găng, có thể làm sau hoặc song song.

---

## Lịch sử thay đổi

| Ngày | Phiên bản | Thay đổi | Người thực hiện |
|---|---|---|---|
| 2026-09-11 | 1.0 | Khởi tạo — 6 story (V-001, BR-001/002/003, MO-001, SY-001) | Hoang Duc |
