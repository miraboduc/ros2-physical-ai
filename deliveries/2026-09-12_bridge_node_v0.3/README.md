---
type: Delivery Note
title: Deliveries — bridge_node v0.3 (2026-09-12)
project: ros2-physical-ai
created_by: Hoang Duc
created_at: 2026-09-12
---

# Gói giao — Bridge Node v0.3 (2026-09-12)

## Đây là gì

Package ROS2 (`bridge_node`) nối `yolo_ros` (nhận diện vật, YOLOv8) với `fanuc_driver`/MoveIt2 (điều khiển tay máy Fanuc) — pipeline: camera thấy vật → tính vị trí 3D → tay máy tự di chuyển tới gần vật.

**Trạng thái**: đã test kỹ trên **simulator** (Gazebo mock hardware, `fanuc_moveit_config`), **CHƯA từng chạy trên robot thật**. Đây là gói gửi để chạy thử lần đầu trên robot thật, theo đúng kịch bản test kèm theo — không phải bản production.

## Nội dung gói

```
bridge_node_source.zip      — toàn bộ source code (ROS2 Python package)
docs/
  user-stories.md            — yêu cầu (6 user story, đã review)
  DDB-bridge-node.md          — thiết kế chi tiết (IEEE1016), 9 business rule, 7 Open Issue
  QA-testcases.csv            — 15 test case (song ngữ VI/JP), tất cả Pass
  review_story_*.md           — review chất lượng user story
  review_code_bridge_node_*.md — review code trước khi giao (1 BLOCKER + 2 MAJOR đã fix)
  TEST-SCENARIO-real-robot-trial.md — KỊCH BẢN TEST CHO KỸ SƯ XƯỞNG — đọc trước khi chạy
evidence/
  rviz_screenshot.png         — ảnh chụp RViz đang chạy simulator (tay máy crx10ia)
  rviz_recording.mp4          — video 15s simulator đang hoạt động
```

## Đọc theo thứ tự này

1. **`docs/TEST-SCENARIO-real-robot-trial.md`** — bắt buộc đọc trước, có phần "Tổng quan" giải thích luồng hoạt động, cảnh báo an toàn, và quy trình test từng bước.
2. **`docs/review_code_bridge_node_20260912.md`** — biết code đã được review gì, còn gì chưa hoàn hảo (mục MINOR còn lại) trước khi tin tưởng 100%.
3. **`docs/DDB-bridge-node.md`** Mục 12 "Open Issues" — 3 giá trị vẫn là placeholder chưa đo thật (`workspace_bounds`, `table_height`, `grasp_orientation`) — **bắt buộc đo lại** trước khi chạy robot thật, xem kịch bản test Mục 2.1.

## Tóm tắt trạng thái kỹ thuật

- 18 unit test + 8 kịch bản integration test trên simulator — tất cả Pass.
- 3 lỗi thật đã tìm ra (qua test + code review) và fix trước khi giao: node treo vô hạn khi action server chết (BR007), gửi lệnh chồng khi camera detect liên tục lúc tay máy đang di chuyển (BR008, kèm 1 race condition tự phát hiện lúc fix — đã sửa bằng lock), chia 0 khi camera chưa calibrate (BR009).
- Model nhận diện hiện tại: YOLOv8 pretrained COCO (80 class có sẵn) — chưa train riêng cho vật của xưởng.
