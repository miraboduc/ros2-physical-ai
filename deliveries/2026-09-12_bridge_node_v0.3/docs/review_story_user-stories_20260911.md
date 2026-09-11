---
type: Review Report
title: Review — docs/requirements/user-stories.md
reviewed_at: 2026-09-11
reviewer: Hoang Duc
---

# Review Report — `docs/requirements/user-stories.md`

## Executive Summary

| Story | Q1-Q5 | Verdict |
|---|---|---|
| US-V-001 | Q5 FAIL (AC4 khác trigger) | ⚠️ NEEDS REVISION |
| US-BR-001 | PASS (AC2 là nhánh input khác, không blocker) | ✅ READY |
| US-BR-002 | PASS (chấp nhận nhóm theo 1 luồng gửi-goal-và-nhận-kết-quả) | ✅ READY |
| US-BR-003 | Q1 FAIL (title/action chứa "or") + thiếu edge case an toàn | ⚠️ NEEDS REVISION |
| US-MO-001 | PASS logic, nhưng mâu thuẫn nội bộ Estimation vs Status | ⚠️ NEEDS REVISION |
| US-SY-001 | PASS (integration story, đã tự giải trình lý do không có SP riêng) | ✅ READY (có ghi chú) |

**Tổng thể**: ⚠️ **NEEDS REVISION** — không có BLOCKER thật sự chặn hiểu/triển khai, nhưng có 3 MAJOR finding nên sửa trước khi coi doc là baseline.

Dependencies/Related/Blocks: **không có broken reference, không có circular dependency** — đối chiếu 2 chiều (Blocks ↔ Dependencies) khớp nhau ở cả 6 story.

---

## Findings

### F-Q5-01 [MAJOR] — US-V-001, AC4 có trigger khác AC1-AC3

**Vị trí**: `US-V-001`, AC4: "Có thể enable/disable node qua service `/yolo/enable`..."
**Vấn đề**: AC1-AC3 đều có trigger "khi có ảnh mới trên camera topic". AC4 có trigger hoàn toàn khác: "operator gọi service /yolo/enable". Đây là 2 hành động khác nhau (Q5 fail).
**Khuyến nghị**: Tách AC4 ra thành story riêng (ví dụ `US-V-002: Enable/disable vision detection`), hoặc — vì US-V-001 chỉ ghi nhận capability của package tái sử dụng (không code mới) — giữ nguyên nhưng đổi AC4 thành ghi chú kỹ thuật ngoài block AC, không tính là acceptance criteria chính thức.

---

### F-Q1-01 [MAJOR] — US-BR-003, title và action chứa liên từ "or"

**Vị trí**: `US-BR-003`, title "Enable or disable the detection-to-motion pipeline"; action "I want to enable or disable the detection-to-motion pipeline"
**Vấn đề**: Q1 (AND/OR test) fail theo đúng nghĩa chữ. Tuy nhiên đây là pattern toggle phổ biến (tương tự "Enable Face ID" trong template gốc, hay chính `/yolo/enable` của yolo_ros) — 1 trigger duy nhất "gọi service với 1 giá trị boolean", 2 nhánh kết quả.
**Khuyến nghị**: Đổi cách diễn đạt để không chứa "or" theo nghĩa đen, ví dụ: title → *"Set pipeline enabled state"*, action → *"I want to set whether the detection-to-motion pipeline is enabled"*. Giữ nguyên cấu trúc AC (2 nhánh true/false) vì đây là coverage angle hợp lệ của 1 trigger, không cần tách story.

---

### F-AC-01 [MAJOR] — US-BR-003, thiếu edge case an toàn: disable giữa lúc đang di chuyển

**Vị trí**: `US-BR-003`
**Vấn đề**: Story không nói rõ hành vi khi operator gọi `/bridge/enable(False)` **trong lúc** tay máy đang thực thi 1 trajectory đã gửi trước đó. Đây là câu hỏi an toàn quan trọng cho robot công nghiệp (dừng ngay giữa đường? hoàn thành trajectory hiện tại rồi dừng?) — không thể để ngầm định.
**Khuyến nghị**: Thêm AC4: *"Khi disable được gọi trong lúc tay máy đang thực thi trajectory, tay máy hoàn thành trajectory hiện tại (không dừng đột ngột giữa đường), sau đó không nhận goal mới cho tới khi enable lại."* (hoặc quyết định khác nếu team muốn dừng ngay — nhưng phải viết rõ, không để trống).

---

### F-Q5-02 [MINOR] — US-BR-003, AC3 (default state khi khởi động) có trigger khác AC1/AC2

**Vị trí**: `US-BR-003`, AC3: "Khi node khởi động lần đầu, pipeline ở trạng thái enable=True..."
**Vấn đề**: Trigger của AC3 là "node khởi động" (system event), khác trigger "operator gọi service" của AC1/AC2. Về nguyên tắc Q5 nghiêm ngặt, đây là 2 loại trigger khác nhau.
**Khuyến nghị**: Không cần tách story (giá trị nhỏ, rủi ro thấp) — nhưng nên gắn nhãn rõ AC3 là "cấu hình khởi tạo" tách biệt khỏi phần "hành vi runtime" (AC1-AC2), để QA viết đúng loại test case (test khởi động node vs. test gọi service).

---

### F-EST-01 [MAJOR] — US-MO-001, mâu thuẫn giữa Estimation và Status

**Vị trí**: `US-MO-001`
**Vấn đề**: Trường Estimation ghi *"0 SP mới trên nguyên lý — **Done** cho phần reuse driver"*, nhưng trường Status ngay dưới lại ghi *"Đã sẵn (clone về) — **chưa build & chưa test trên Gazebo**, chưa Done thật sự"*. Hai trường mâu thuẫn nhau về việc story này đã Done hay chưa.
**Khuyến nghị**: Sửa Estimation thành thống nhất với Status, ví dụ: *"0 SP code mới (100% reuse `fanuc_driver`), nhưng cần công việc tích hợp/verify (build + test trên Gazebo) — ước lượng riêng 2 SP cho phần verify này, chưa tính Done."* Đổi Status thành `Backlog` (không phải Done) cho tới khi build+test xong trên Gazebo — khớp với ma trận dependencies (US-BR-002 đang chặn bởi story này).

---

### F-Q5-03 [MINOR] — US-MO-001, AC3 là hành vi liên tục không cùng trigger với AC1/AC2

**Vị trí**: `US-MO-001`, AC3: "Trạng thái khớp hiện tại luôn publish liên tục trên /joint_states..."
**Vấn đề**: AC1/AC2 có trigger "nhận goal". AC3 là hành vi background liên tục, độc lập với việc có goal hay không.
**Khuyến nghị**: Vì đây là story ghi nhận capability có sẵn (không code mới), giữ nguyên nhưng nếu sau này tách story cho phần dev mới (ví dụ viết custom hardware_interface), nên tách AC3 thành story riêng "Publish joint state liên tục".

---

### W-ROLE-01 [MINOR] — US-SY-001, vai trò "Robot Operator" nhưng trigger là sự kiện môi trường/hệ thống

**Vị trí**: `US-SY-001`
**Vấn đề**: "As a Robot Operator / I want to see the robot arm move..." — hành động thực tế được kích hoạt bởi camera nhìn thấy vật thể (sự kiện hệ thống), không phải Operator bấm nút. Role "Operator" ở đây là người quan sát/xác nhận, không phải actor khởi tạo trigger.
**Khuyến nghị**: Không cần sửa (đây là pattern hợp lệ cho integration/acceptance story trong robotics — Operator là actor "chấp nhận kết quả", không phải actor kích hoạt). Chỉ nên ghi chú rõ trong story: *"Trigger: sự kiện môi trường (object xuất hiện trong tầm nhìn camera), không phải hành động của Operator."* để tránh nhầm lẫn khi QA viết test.

---

### W-EST-01 [MINOR] — US-SY-001, không có Estimation dạng số

**Vị trí**: `US-SY-001`, Estimation: "—"
**Vấn đề**: Phase 4 yêu cầu mọi story có SP 1-8. US-SY-001 để trống với lý do đã giải trình (rollup của BR-001+BR-002+MO-001).
**Khuyến nghị**: Chấp nhận được cho integration/acceptance story — đây là thực hành phổ biến (epic/checkpoint không có SP riêng). Không cần sửa, giữ nguyên ghi chú giải trình đã có.

---

## Relationship Validation

✅ Không có dependency không tồn tại, không có circular dependency.
✅ Đối chiếu Blocks ↔ Dependencies khớp nhau ở mọi story (V-001→BR-001, BR-001→BR-002/SY-001, BR-002→SY-001, MO-001→BR-002).
ℹ️ Module code (V, BR, MO, SY) không có trong REG-code.md chính thức (dự án chưa có file này) — nhưng đã tự định nghĩa rõ trong bảng "Module ID" của chính doc, coi như tạm chấp nhận cho tới khi có REG-code chính thức.

## Estimation Analysis

| Story | SP | Đánh giá |
|---|---|---|
| BR-001 | 5 | Hợp lý (tf2 + calibration + depth handling = độ phức tạp cao) |
| BR-002 | 5 | Hợp lý (action client + safety check + error handling) |
| BR-003 | 2 | Thấp so với mức an toàn cần thiết — nên tăng lên 3 SP sau khi thêm AC edge-case (F-AC-01) |
| MO-001 | Mâu thuẫn | Xem F-EST-01 |
| SY-001 | — (rollup) | Chấp nhận được, đã giải trình |

## Verdict

⚠️ **NEEDS REVISION** — 3 MAJOR finding (F-Q5-01, F-Q1-01, F-AC-01, F-EST-01) nên sửa trước khi dùng doc này làm baseline cho code. Không có gì chặn việc hiểu tổng thể pipeline hoặc bắt đầu code — có thể sửa song song trong lúc bắt đầu implement US-BR-001.

## Recommended fixes (áp dụng ngay)

1. US-V-001: chuyển AC4 thành ghi chú kỹ thuật, không tính là AC chính thức.
2. US-BR-003: đổi title/action tránh "or"; thêm AC edge-case disable-giữa-đường; tăng estimation → 3 SP.
3. US-MO-001: sửa Status/Estimation cho nhất quán — story này thực chất là **Backlog** (chưa build+test), không phải Done.
