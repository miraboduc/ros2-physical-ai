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

## ⚠️ Lưu ý quan trọng — gói này KHÔNG tự chạy được ngay

`bridge_node` chỉ là 1 trong 3 phần cần có (phần do Mirabo viết). **`yolo_ros`** (nhận diện) và **`fanuc_driver`** (điều khiển tay máy) là 2 source code khác, tải từ GitHub, PHẢI tự clone + build riêng — không có trong zip này (không đóng gói lại code của bên khác). Xem hướng dẫn đầy đủ ở `docs/SETUP-INSTALL-GUIDE.md` — làm theo đúng thứ tự đó trước khi chạy `bridge_node`.

## Nội dung gói

```
bridge_node_source.zip      — source code CỦA MIRABO (ROS2 Python package) — chỉ 1/3 phần cần có
docs/
  SETUP-INSTALL-GUIDE.md      — BẮT BUỘC ĐỌC TRƯỚC — cài đủ cả 3 phần (yolo_ros, fanuc_driver, bridge_node)
  user-stories.md            — yêu cầu (6 user story, đã review)
  DDB-bridge-node.md          — thiết kế chi tiết (IEEE1016), 9 business rule, 7 Open Issue
  QA-testcases.csv            — 15 test case (song ngữ VI/JP), tất cả Pass
  review_story_*.md           — review chất lượng user story
  review_code_bridge_node_*.md — review code trước khi giao (1 BLOCKER + 2 MAJOR đã fix)
  TEST-SCENARIO-real-robot-trial.md — KỊCH BẢN TEST CHO KỸ SƯ XƯỞNG — đọc trước khi chạy
evidence/
  rviz_screenshot.png         — ảnh chụp RViz đang chạy simulator (tay máy crx10ia)
  rviz_recording.mp4          — video simulator đang hoạt động (xem ghi chú evidence trong file cùng tên .md nếu có)
```

## Đọc theo thứ tự này

1. **`docs/SETUP-INSTALL-GUIDE.md`** — cài đủ môi trường trước (yolo_ros + fanuc_driver + bridge_node), không chỉ giải nén zip này.
2. **`docs/TEST-SCENARIO-real-robot-trial.md`** — bắt buộc đọc trước khi chạy, có phần "Tổng quan" giải thích luồng hoạt động, cảnh báo an toàn, và quy trình test từng bước.
3. **`docs/review_code_bridge_node_20260912.md`** — biết code đã được review gì, còn gì chưa hoàn hảo (mục MINOR còn lại) trước khi tin tưởng 100%.
4. **`docs/DDB-bridge-node.md`** Mục 12 "Open Issues" — 3 giá trị vẫn là placeholder chưa đo thật (`workspace_bounds`, `table_height`, `grasp_orientation`) — **bắt buộc đo lại** trước khi chạy robot thật, xem kịch bản test Mục 2.1.

## Tóm tắt trạng thái kỹ thuật

- 18 unit test + 8 kịch bản integration test trên simulator — tất cả Pass.
- 3 lỗi thật đã tìm ra (qua test + code review) và fix trước khi giao: node treo vô hạn khi action server chết (BR007), gửi lệnh chồng khi camera detect liên tục lúc tay máy đang di chuyển (BR008, kèm 1 race condition tự phát hiện lúc fix — đã sửa bằng lock), chia 0 khi camera chưa calibrate (BR009).
- Model nhận diện hiện tại: YOLOv8 pretrained COCO (80 class có sẵn) — chưa train riêng cho vật của xưởng.
