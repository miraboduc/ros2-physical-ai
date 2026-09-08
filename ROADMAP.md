# Lộ trình học ROS 2 + Python → tích hợp Fanuc qua Jetson

Mục tiêu cuối: hệ thống nhận diện object (画像解析, chạy trên GPU) hoạt động **song song** với chuyển động cánh tay Fanuc, không để robot dừng chờ kết quả nhận diện giữa thao tác — giảm thời gian chờ mỗi chu kỳ khoảng 2-3s.

Bối cảnh đã chốt:
- Môi trường: dual-boot Ubuntu 22.04 (khớp JetPack 6 trên Jetson → giảm rủi ro "chạy được trên PC, lỗi trên Jetson")
- ROS 2 Humble (LTS, tương thích Isaac ROS/Isaac Sim hiện tại — cần double-check version matrix tại thời điểm cài vì các bản này cập nhật thường xuyên)
- Simulator: Gazebo trước (học core ROS2 + motion control), Isaac Sim sau (GPU-accelerated perception, khớp hướng "physical AI")
- Xuất phát điểm: mới với ROS2, vững Python
- Tốc độ: học kèm dự án thực tế, ưu tiên phần liên quan trực tiếp Fanuc + vision song song

Timeline dưới đây là ước lượng làm việc tập trung (không phải học nhẹ nhàng cuối tuần) — tổng khoảng 3-4 tuần tới lúc có kiến trúc chạy được trên simulator, phần tích hợp Fanuc thật (Phase 5) phụ thuộc thiết bị thực tế nên không cam kết mốc cứng.

---

## Phase 0 — Môi trường (1-2 ngày)

- Dual-boot Ubuntu 22.04 LTS
- Cài driver NVIDIA + CUDA toolkit (native, không qua lớp ảo hoá nên đơn giản hơn WSL2)
- Cài ROS 2 Humble (apt)
- Cài Gazebo Classic 11 + `ros_gz`/`gazebo_ros_pkgs` tương ứng Humble
- Verify: `ros2 doctor`, chạy demo `turtlesim`

**Output cần đạt**: `colcon build` một workspace rỗng chạy không lỗi, GPU nhận bởi `nvidia-smi` trên Ubuntu.

## Phase 1 — ROS 2 core cho Python dev (3-5 ngày)

Học qua thực hành trực tiếp, không học lý thuyết suông:

- `rclpy`: node, publisher/subscriber, custom message/service
- Service vs Action — Action là async, đây là nền tảng bắt buộc cho kiến trúc song song ở Phase 4
- Executor: SingleThreaded vs MultiThreaded, Callback Group (Reentrant/MutuallyExclusive) — giới thiệu sớm dù là "cơ bản" vì đây chính là cơ chế cho phép vision callback và motion callback chạy đồng thời trong cùng 1 process
- Launch file (Python), parameters, cấu trúc workspace `colcon`
- `tf2`: frame, broadcaster/listener (camera_frame → robot_base_frame → tool_frame)

**Bài tập bắt buộc**: 2 node độc lập — node A publish "fake detection" 10Hz, node B là action client giả lập chuyển động, cả hai chạy không chặn nhau. Đây là mô hình thu nhỏ của bài toán thật.

## Phase 2 — Mô phỏng cánh tay công nghiệp trên Gazebo (3-5 ngày)

- URDF/Xacro cho robot 6 trục (dùng URDF có sẵn của ros-industrial để học pattern trước; URDF chính xác của model Fanuc thật cần kiểm tra ở Phase 5)
- `ros2_control`: controller_manager, JointTrajectoryController, hardware_interface abstraction — **quan trọng**: đây là lớp trừu tượng sau này chỉ cần thay "simulated hardware interface" bằng interface nói chuyện với Fanuc thật, code phía trên tái dùng gần như nguyên vẹn
- MoveIt2 cơ bản: planning scene, joint-space/Cartesian planning, gọi qua Action (MoveGroup) — không chỉ click RViz, phải tự viết Python node gọi action
- **Bài tập**: node Python tự viết gửi waypoint và thực thi trajectory qua `FollowJointTrajectory` action, không qua GUI

## Phase 3 — Object detection GPU (画像解析) (3-5 ngày, có thể học song song Phase 2)

- Model: YOLOv8 (ultralytics), pretrained COCO để demo nhanh, fine-tune sau nếu object đặc thù
- Test trên PC GPU bằng PyTorch trước, sau đó export TensorRT (bắt buộc cho tốc độ, và bắt buộc phải build lại engine riêng trên Jetson vì kiến trúc ARM khác x86 — engine build trên PC không chạy thẳng trên Jetson được)
- Đóng gói thành ROS2 node: subscribe camera topic → publish `Detection2DArray`/pose. Cần calibrate camera intrinsics + tf2 để chuyển bbox 2D → pose 3D trong `robot_base_frame`
- **Đo latency thực tế** capture → inference → publish. Con số này quyết định còn giảm được bao nhiêu giây ở Phase 4.

## Phase 4 — Kiến trúc song song Vision + Motion (lõi bài toán, 3-5 ngày)

Vấn đề hiện tại (giả định): di chuyển tới điểm quan sát → dừng → chụp → **chờ đồng bộ** kết quả nhận diện → mới di chuyển tiếp → mất 2-3s/chu kỳ.

Giải pháp (làm từng bước cùng nhau):

1. **Multi-threaded executor + Reentrant callback group**: vision callback và motion feedback callback chạy đồng thời trong cùng process, không xếp hàng chờ nhau (Phase 1 đã học nền).
2. **Pipeline/lookahead**: bắt đầu chụp+detect cho vị trí/object kế tiếp **ngay khi** tay máy bắt đầu di chuyển tới đó, thay vì đợi tới nơi mới chụp — tận dụng thời gian di chuyển (thường vốn đã vài trăm ms tới vài giây) để "giấu" thời gian inference.
3. **Shared "latest detection" state**: motion node đọc detection mới nhất ngay trước khi thực thi trajectory cuối (qua topic QoS phù hợp hoặc lock), thay vì gọi service đồng bộ chờ kết quả.
4. **Dự đoán vị trí nếu object di chuyển** (băng chuyền...): Kalman filter/extrapolate theo timestamp để bù độ trễ giữa lúc detect và lúc tay tới nơi.
5. **Tối ưu bản thân inference** (TensorRT, giảm resolution) — nếu inference chỉ còn 50-100ms thì kiến trúc pipeline ở trên gần như xoá sạch độ trễ nhìn thấy được.

**Bài tập**: đo chu kỳ pick-and-place trước/sau khi áp dụng kiến trúc trên Gazebo, so với mục tiêu giảm 2-3s.

## Phase 5 — Tích hợp Fanuc thật qua Jetson (mốc thời gian phụ thuộc thiết bị thực tế)

**Chưa xác định — cần kiểm tra trực tiếp trước khi code, không giả định**:
- Model controller Fanuc cụ thể (R-30iB / R-30iB Plus / R-30iB Mate...)
- Phương thức giao tiếp controller đã có sẵn: PC Interface, KAREL, Ethernet/IP, hay có driver ROS2 chính thức nào (ros-industrial hoặc Fanuc cung cấp) hỗ trợ đúng model này
- Phiên bản JetPack trên Jetson thực tế, khớp ROS2 distro nào

Khi xác nhận xong, áp dụng đúng pattern `ros2_control hardware_interface` đã học Phase 2 — chỉ thay phần "simulated" bằng phần nói chuyện với controller Fanuc thật, code Phase 2-4 tái dùng gần như nguyên vẹn. Vision node deploy lên Jetson cần build lại TensorRT engine trên chính Jetson.

---

## Cách làm việc cùng nhau

Mỗi phase: tôi giải thích khái niệm ngắn gọn → viết code mẫu cùng bạn → bạn chạy thử trên máy → đo/kiểm tra kết quả thực tế trước khi qua phase tiếp theo (không chuyển phase chỉ dựa trên "chắc đúng rồi", theo đúng nguyên tắc luôn xác thực bằng chạy thật).
