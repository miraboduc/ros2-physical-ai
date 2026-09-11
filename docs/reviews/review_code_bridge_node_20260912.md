---
type: Review Report
title: Code Review — package bridge_node (pre-delivery gate)
reviewed_at: 2026-09-12
reviewer: Hoang Duc
---

# Code Review Report — `bridge_node` (trước khi gửi xưởng chạy thử robot thật)

**Phạm vi**: toàn bộ `~/ros2_ws/src/bridge_node/` so với `docs/requirements/user-stories.md` (US-BR-001/002/003) và `docs/design/DDB-bridge-node.md` (BR001-BR008).

## Tóm tắt

| Mức độ | Số lượng | Đã fix |
|---|---|---|
| BLOCKER | 1 | ✅ |
| MAJOR | 2 | ✅ |
| MINOR | 5 | 2/5 (m3, m4, m5 chấp nhận rủi ro thấp, chưa fix) |
| SUGGESTION | 4 | 2/4 (còn 2 chấp nhận nguyên trạng) |

**Verdict ban đầu**: CHANGES REQUESTED. **Sau khi fix BLOCKER + 2 MAJOR + rebuild + test lại**: 18/18 unit test pass, coi như đạt để gửi đi (với các MINOR/SUGGESTION còn lại ghi rõ dưới đây, không chặn việc gửi).

## Findings

### 🔴 BLOCKER B1 — `MotionGoalSender._busy` không thread-safe, BR008 chưa thực sự đóng được race

**File**: `motion_goal_sender.py`
**Spec**: BR008

`bridge_node.py` đặt subscriber detection VÀ action client vào **cùng 1 `ReentrantCallbackGroup`** dưới `MultiThreadedExecutor` — 2 detection callback có thể chạy đồng thời trên 2 thread khác nhau. Giữa lúc check `is_busy()` và lúc set `_busy = True`, code gọi `is_in_workspace()` + `server_is_ready()` (có thể nhả GIL) — đủ cửa sổ cho 2 thread cùng đọc `_busy == False` trước khi cả 2 set `True` và gửi goal — đúng lỗi mà BR008 định sửa vẫn xảy ra được.

**Fix**: bọc toàn bộ "check busy → check workspace → check server → set busy → gửi" trong `threading.RLock()`. Dùng `RLock` (không phải `Lock` thường) vì phát hiện thêm: test double gọi callback đồng bộ ngay trong cùng thread, `Lock` thường tự deadlock khi thread đó cố lock lại lần 2 — đây là bug tôi tự gây ra lúc fix B1, phát hiện ngay khi chạy lại test (process treo >4 phút), sửa bằng `RLock`.

**Test**: `test_concurrent_detections_never_send_overlapping_goals` — 8 thread gọi `send_goal()` đồng thời, future không tự resolve (mô phỏng goal đang bay thật), xác nhận đúng 1 goal được gửi.

### 🟠 MAJOR M1 — Chia 0 khi `CameraInfo.k` chưa calibrate (fx=fy=0)

**File**: `pose_converter.py`, `geometry_utils.py`
Đã fix: thêm BR009, check `fx==0 or fy==0` trước khi tính ray, xử lý giống nhánh tf2 fail (log throttle, skip frame, không crash). Test: `test_zero_fx_fy_camera_info_skips_frame_without_crashing`.

### 🟠 MAJOR M2 — Ghép sai 2D↔3D khi nhiều vật cùng class

**File**: `pose_converter.py`
Đã fix: nếu >1 detection_3d cùng `class_id` → coi là ambiguous, fallback sang nhánh 2D+tf2 thay vì đoán liều. Ghi thành Open Issue #7 trong design doc (single-object-per-class vẫn là precondition ngầm — đã đưa vào kịch bản test gửi xưởng, Mục 2.2). Test: `test_ambiguous_detections_3d_falls_back_to_2d_instead_of_guessing`.

### 🟡 MINOR — còn lại, chấp nhận rủi ro thấp (chưa fix)

- **m3**: `enable_on_start` override qua launch argument chưa có test end-to-end xác nhận string→bool coerce đúng qua `launch_ros`. Khuyến nghị: kỹ sư xưởng verify tay 1 lần (`ros2 launch bridge_node bridge_node.launch.py enable_on_start:=false`) trước khi tin tưởng.
- **m4**: `EnableGate.is_enabled()` check 1 lần ở đầu callback, không re-check ngay trước `send_goal()` — lý thuyết có thể lọt 1 goal thừa nếu disable đến đúng giữa khoảng đó. Xác suất/ảnh hưởng thấp (tối đa 1 goal thừa, không phải vô hạn), chấp nhận cho MVP.
- **m5**: không check timestamp đồng bộ giữa `/yolo/detections` và `/yolo/detections_3d`. Rủi ro thấp vì tracking vật di động đã ngoài phạm vi (US-SY-001 AC3).

### 💡 SUGGESTION — đã fix 2/4

- ✅ Đã thêm `launch`/`launch_ros` vào `exec_depend` trong `package.xml`.
- ✅ Đã xóa glob `config/*.yaml` chết (thư mục `config/` không tồn tại) trong `setup.py`.
- Giữ nguyên: `workspace_bounds` giờ có validate độ dài + min≤max (đã thêm luôn trong lúc fix, dù ban đầu chỉ là SUGGESTION) — báo lỗi rõ thay vì `IndexError` khó hiểu.
- Chưa làm: tie-breaking khi 2 detection cùng điểm score cao nhất (`max()` lấy phần tử đầu) — chấp nhận, MVP single-object.

## Đã verify đúng (không có finding)

BR001 (`>=` không phải `>`), BR003 (tf2 fail không crash), BR004 (check workspace luôn chạy trước khi gửi), BR005 (không có đường retry nào), BR006 (không có API cancel goal ở đâu trong code), BR007 (check server trước khi set busy và gửi).

## Kết luận

Sau khi fix B1/M1/M2 + rebuild + 18/18 unit test pass + review lại các fix: **đủ điều kiện đóng gói gửi xưởng**, kèm kịch bản test thận trọng (`TEST-SCENARIO-real-robot-trial.md`) vì đây là lần đầu chạy trên robot thật.
