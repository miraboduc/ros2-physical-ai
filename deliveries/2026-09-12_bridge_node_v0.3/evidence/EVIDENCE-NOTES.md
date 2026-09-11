---
type: Evidence Notes
title: Ghi chú evidence — bằng chứng tay máy di chuyển thật trên simulator
project: ros2-physical-ai
created_by: Hoang Duc
created_at: 2026-09-12
---

# Ghi chú evidence (2026-09-12)

**Bối cảnh quan trọng**: lần chụp/quay đầu tiên (2026-09-11) đã bị loại bỏ vì không xác nhận trước có chuyển động thật xảy ra hay không — phát hiện nhờ câu hỏi trực tiếp của Hoang Duc khi xem lại. Bộ evidence này (2026-09-12) được làm lại có kiểm chứng số liệu ở cả 2 đầu, không chỉ dựa vào hình ảnh.

## File trong bộ này

- `rviz_motion_proof.mp4` — video 12s quay cửa sổ RViz trong lúc gửi 1 detection hợp lệ tới Bridge Node.
- `before_motion.png` — frame đầu video.
- `after_motion.png` — frame cuối video (thấy rõ khớp dưới của tay máy đổi hướng so với frame đầu).
- `status_proof.log` — log topic `/bridge/status` bắt được trong lúc quay: `executing`.

## Bằng chứng số liệu (không chỉ nhìn hình)

**`/joint_states` TRƯỚC khi publish detection cho video này** (giá trị của lần test trước đó, dùng làm điểm xuất phát):
```
position: [-1.9508, -1.0681, 3.8161, 1.9268, 1.6413, -0.1166]
```

**`/joint_states` SAU khi video kết thúc**:
```
position: [0.1200, -1.0017, 3.6729, -0.0860, 1.6489, 0.0082]
```

→ Cả 6 khớp đều đổi giá trị rõ rệt (không phải sai số làm tròn) — xác nhận tay máy **thực sự di chuyển**, không phải hình ảnh tĩnh.

## Quy trình verify (để ai đọc lại cũng tái tạo được)

1. Đọc `/joint_states` — ghi lại làm baseline.
2. Bắt đầu quay `ffmpeg` (x11grab đúng vùng cửa sổ RViz) + đồng thời echo `/bridge/status` ra file.
3. Publish 1 message `/yolo/detections` với pixel đã tính trước để ra 1 pose khác pose hiện tại, nằm trong `workspace_bounds` cấu hình.
4. Dừng quay, đọc lại `/joint_states` — so sánh với baseline.
5. Trích frame đầu/cuối video, so sánh trực quan — khớp với số liệu.

**Giới hạn của bộ evidence này**: vẫn là simulator (mock hardware), không phải robot thật; pose test là point tính tay từ pixel cụ thể, không phải qua toàn bộ pipeline camera thật → yolo_ros thật (dù logic xử lý bên trong `bridge_node` giống hệt, chỉ khác nguồn input).
