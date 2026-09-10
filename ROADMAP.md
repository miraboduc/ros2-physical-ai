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
- GPU thực tế: **RTX 3090 (24GB, Ampere)**. Đã research 2026-09-10 (xem Phụ lục B): tổ hợp RTX 3090 + Ubuntu 22.04 + **Isaac Sim 4.5** (không phải bản 5.1/6.0 mới nhất, bản đó tối thiểu yêu cầu RTX 4080) đã có người cài chạy được trên thực tế, không chỉ suy đoán từ bảng spec.
  - Driver NVIDIA: **≥ 575.57.08** (có báo cáo Isaac Sim 4.5 crash với driver 550, nên tránh bản driver mặc định cũ trong apt)
  - CUDA: **≥ 12.2**
  - Vẫn có báo cáo hiệu năng thấp (~9fps) ở một số cấu hình dù phần cứng "recommended" ở bản mới — nghĩa là "cài chạy được" chứ chưa chắc "mượt", phải tự đo FPS trên scene thật của bạn ở cuối phase này, không giả định.
- Cài ROS 2 Humble (apt)
- Cài Gazebo Classic 11 + `ros_gz`/`gazebo_ros_pkgs` tương ứng Humble
- Verify: `ros2 doctor`, chạy demo `turtlesim`

**Output cần đạt**: `colcon build` một workspace rỗng chạy không lỗi, GPU nhận bởi `nvidia-smi` trên Ubuntu (kiểm tra đúng driver ≥ 575.57.08), và nếu cài Isaac Sim 4.5 ở bước này/Phase 2 thì đo FPS thực tế trên 1 scene đơn giản trước khi tin tưởng dùng cho phase sau.

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

**Cập nhật 2026-09-10 (đã research, xem Phụ lục B)**: Fanuc có driver ROS2 chính thức — repo `fanuc_driver` (fanuc-corporation.github.io/fanuc_driver_doc), dùng `ros2_control` streaming driver. Tuy nhiên **danh sách model được xác nhận hỗ trợ trong tài liệu chỉ là dòng cobot CRX** (CRX-3iA/5iA/10iA/10iA-L/20iA-L/30iA), không phải toàn bộ dòng công nghiệp Fanuc. Vẫn **chưa xác định — cần kiểm tra trực tiếp trước khi code**:
- Model robot Fanuc thực tế của dự án có nằm trong danh sách CRX được driver hỗ trợ không (nếu là dòng công nghiệp khác như M-20iA/R-2000iC..., driver này có thể không áp dụng được, cần hỏi lại Fanuc/tài liệu controller cụ thể)
- Controller có đúng phiên bản phần mềm yêu cầu không: R-30iB Plus/Mate Plus ≥ V9.40P/81, R-30iB Mini Plus ≥ V9.40P/77, R-50iA ≥ V10.10P/26
- Controller đã có option "Stream Motion (J519) + Remote Motion (R912)" hoặc gói "S636 External Control Package" chưa — đây là software option phải mua/kích hoạt riêng trên Fanuc, không tự có sẵn
- Driver docs ghi ROS 2 Jazzy (có nhánh Humble) — cần đối chiếu với ROS2 distro thật sự chạy trên Jetson (JetPack version) trước khi chốt distro ở Phase 0, có thể phải đổi từ Humble sang Jazyy tuỳ kết quả kiểm tra
- Phiên bản JetPack trên Jetson thực tế, khớp ROS2 distro nào

Nếu robot thật **không** thuộc dòng CRX hoặc controller không có software option trên, quay lại hướng cũ (PC Interface/KAREL/Ethernet-IP tự viết bridge) — không giả định driver chính thức chắc chắn dùng được cho tới khi kiểm tra xong.

Khi xác nhận xong, áp dụng đúng pattern `ros2_control hardware_interface` đã học Phase 2 — chỉ thay phần "simulated" bằng phần nói chuyện với controller Fanuc thật, code Phase 2-4 tái dùng gần như nguyên vẹn. Vision node deploy lên Jetson cần build lại TensorRT engine trên chính Jetson.

---

## Cách làm việc cùng nhau

Mỗi phase: tôi giải thích khái niệm ngắn gọn → viết code mẫu cùng bạn → bạn chạy thử trên máy → đo/kiểm tra kết quả thực tế trước khi qua phase tiếp theo (không chuyển phase chỉ dựa trên "chắc đúng rồi", theo đúng nguyên tắc luôn xác thực bằng chạy thật).

---

## Phụ lục B — Phân tích quy trình quét 3D xây môi trường giả lập (research 2026-09-10)

Đây là research đối chiếu bản đề xuất 4 bước của bạn với tình trạng thực tế của các công cụ (đã kiểm tra qua tài liệu chính thức/nguồn web tháng 9/2026, không suy đoán). Kết quả này **thay thế nội dung Phase 2** ở trên bằng bản chi tiết hơn cho phần "xây môi trường xưởng thật", còn phần "học ROS2 core với URDF mẫu" ở Phase 2 vẫn giữ nguyên làm bước khởi động trước khi làm phần này.

### Bước 1 — Quét bằng iPhone: đúng phần lớn, có 1 điểm cần sửa

- **Scaniverse xác nhận đúng**: miễn phí, không giới hạn số lần quét, xử lý on-device. Nhưng cần phân biệt 2 loại export: (a) Gaussian Splatting (PLY/SPZ) — chỉ để xem/render đẹp, **không có mesh/collision, không dùng được cho vật lý**; (b) Mesh workflow (OBJ/FBX/**GLB**/USDZ) — đây mới là thứ cần cho bước 3 (baking collider). Khi quét, phải chọn export mesh, không phải export splat.
- **Polycam free tier bị giới hạn 150 ảnh/model** — nếu xưởng rộng, 150 ảnh có thể không đủ độ phân giải, nên Scaniverse vẫn là lựa chọn tốt hơn cho trường hợp này như bạn đã đề xuất.
- **Rủi ro chưa nêu trong đề xuất gốc**: mesh từ scan điện thoại (LiDAR/photogrammetry) có sai số thực tế ở mức cm, có ghi nhận trường hợp mesh bị méo, thiếu lỗ hổng, sai tỷ lệ tới ~17% nếu không hậu xử lý. Vì vậy:
  - Mesh xưởng (tường, sàn, bàn, vật cản cố định) dùng scan là ổn cho mục đích collision thô.
  - Vật thể robot cần **gắp chính xác** (hộp hàng, linh kiện nhỏ) thì **không nên dùng mesh scan trực tiếp** — nên dùng CAD thật hoặc primitive shape (box/cylinder) với kích thước đo tay, vì sai số cm của scan đủ làm gripper tính toán sai vị trí gắp.
  - Luôn phải re-check scale (bước bạn đã nêu ở Bước 3.2) bằng cách đo 1 khoảng cách thật ngoài đời rồi so với model — bắt buộc, không phải tuỳ chọn.

### Bước 2 — Chọn engine: cần sửa lại, không nên coi PyBullet/MuJoCo là 2 lựa chọn ngang hàng

- **PyBullet: không còn được maintain tích cực** — không có bản release mới trên PyPI trong ~12 tháng qua, cộng đồng coi là gần như ngừng phát triển.
- **MuJoCo: đang phát triển tích cực** — được Google DeepMind mua lại và mã nguồn mở từ 2022, license Apache 2.0, bản ổn định gần nhất 3.2.7 (2025).
- **Phát hiện quan trọng chưa có trong đề xuất gốc**: đã có package `mujoco_ros2_control` chính thức nằm trong hệ sinh thái `ros2_control` (tài liệu tại control.ros.org, cả nhánh Jazzy và Rolling) — tức là MuJoCo giờ dùng **đúng cùng abstraction `ros2_control`** mà Phase 2 của roadmap này đã dạy, và đúng abstraction mà Phase 5 sẽ dùng để nói chuyện với Fanuc thật. Điều này khớp thẳng với nguyên tắc "code Phase 2-4 tái dùng gần như nguyên vẹn" đã đặt ra.
- **Kết luận**: nếu muốn hướng "nhẹ, thuần Python" như đề xuất gốc, chọn **MuJoCo**, không chọn PyBullet.
- **Nhưng cần lưu ý**: MuJoCo/PyBullet đều **không có pipeline import ảnh quét glTF → chuyển vật liệu/scale tự động** tốt như Isaac Sim — quy trình "quét xưởng thật → import" ở đề xuất gốc thực chất chỉ khớp tốt với Isaac Sim (USD-native, có Mesh Importer glTF→USD giữ material). Nếu chọn MuJoCo cho phần vật lý robot, môi trường xưởng quét được vẫn nên là asset phụ trợ (visual/collision tĩnh), không kỳ vọng workflow tự động mượt như Isaac Sim.
- **Isaac Sim + GPU thật (RTX 3090, 24GB) — đã kiểm tra 2026-09-10**: bản mới nhất (5.1) liệt kê **RTX 4080 16GB là mức tối thiểu chính thức**, và RTX 3090 (kiến trúc Ampere 2020) không nằm trong danh sách phần cứng được test cho bản này. Nhưng đây **không phải giới hạn kỹ thuật cứng** — RTX 3090 vẫn có RT Core (không thuộc nhóm bị chặn hẳn như A100/H100) và có 24GB VRAM, tức nhiều hơn cả mức tối thiểu 16GB nêu trong docs. Thực tế trên forum NVIDIA: 1 người dùng RTX 3090 chạy Isaac Sim 4.5.0 báo cáo chỉ ~9fps ở 1 cấu hình được cho là "recommended hardware" — không tệ tới mức không chạy được, nhưng hiệu năng render không được đảm bảo/không tối ưu ở bản mới nhất.
  - **Kết luận đúng mức**: chưa xác nhận được RTX 3090 "không chạy được" Isaac Sim — mới xác nhận được là **không nằm trong phần cứng được test/support chính thức ở bản 5.1**, hiệu năng có báo cáo thấp ở ít nhất 1 trường hợp thực tế.
  - **Đề xuất cụ thể**: (a) thử cài bản Isaac Sim cũ hơn (dòng 4.x) — bản này có mức tối thiểu công bố là RTX 3070 8GB, tức RTX 3090 24GB vượt xa mức đó, khả năng chạy ổn cao hơn; hoặc (b) tự test trực tiếp trên máy bạn (Isaac Sim miễn phí, không tốn phí để thử) và đo FPS thực tế cho đúng use-case của bạn (1 robot, 1-2 camera, không phải RL training song song hàng chục môi trường như case 9fps ở trên); nếu chậm, roadmap đã có sẵn phương án dự phòng là **MuJoCo + `mujoco_ros2_control`** (nhẹ hơn nhiều, không cần photoreal rendering).
  - **Cập nhật 2026-09-10 (xác nhận thêm)**: tìm được nhiều hướng dẫn cài đặt cộng đồng cụ thể đúng tổ hợp **RTX 3090 + Ubuntu 22.04 + Isaac Sim 4.5** — tức đây là combo đã có người cài chạy thành công trên thực tế, không chỉ suy luận từ bảng spec. Lưu ý khi cài: có báo cáo Isaac Sim 4.5 bị crash với driver NVIDIA 550, nên dùng **driver ≥ 575.57.08** và **CUDA ≥ 12.2**. Vẫn có báo cáo ~9fps ở một số cấu hình dù phần cứng "recommended" — nên coi đây là "cài chạy được, hiệu năng phải tự đo" chứ chưa phải "chắc chắn mượt". Đã đưa version cụ thể này vào Phase 0.
- **License Isaac Sim — cần lưu ý vì đây là dự án cho khách hàng (Fanuc/Mirabo), không phải side-project cá nhân**: Isaac Sim mã nguồn mở (Apache 2.0) và miễn phí cho R&D nội bộ, kể cả khi output (video, report, data) được giao cho khách hàng. Chỉ cần license Enterprise nếu **đóng gói/phân phối lại chính Isaac Sim** hoặc **cung cấp Isaac Sim như 1 dịch vụ** cho bên thứ ba. Việc dùng nội bộ để dev/test rồi giao sản phẩm cuối (driver, code, data) cho khách vẫn thuộc diện miễn phí — nhưng nếu phạm vi hợp đồng có thay đổi (vd giao luôn cả simulator cho khách dùng), nên xác nhận lại với NVIDIA/đọc kỹ license FAQ tại thời điểm đó chứ không suy đoán tiếp từ ghi chú này.

### Bước 3 — Cấu hình vật lý: đúng ý tưởng, sai thuật ngữ + thiếu 1 bước

- "Baking Collider" không phải thuật ngữ của Isaac Sim (đó là thuật ngữ Unity/Unreal). Trong Isaac Sim gọi là **Collision Approximation**, với các lựa chọn cụ thể: `convexHull`, `convexDecomposition`, `boundingCube`, `boundingSphere`, `sdf`. Cho mesh xưởng phức tạp (tường, kệ, vật cản không lồi), nên dùng `convexDecomposition` hoặc `sdf` — `convexHull` đơn sẽ làm vật cản bị "phồng lồi" sai hình dạng thật.
- Thiếu 1 bước quan trọng trước khi bake collider: **dọn mesh** (decimate giảm số tam giác, fill hole, kiểm tra normal) vì mesh scan điện thoại thường có lỗ hổng/nhiễu như đã nêu ở Bước 1 — bake collider trực tiếp trên mesh scan thô dễ tạo collision shape sai hoặc engine vật lý bị lỗi khi build convex decomposition.
- Phần "Định nghĩa Robot bằng URDF" đúng — và tin tốt: dòng cobot CRX của Fanuc **đã có URDF chính thức** trong repo `fanuc_driver` (package `fanuc_crx_description`), không cần tự vẽ lại từ đầu nếu robot thật là CRX (xem Phase 5).

### Bước 4 — ROS2 Python: đúng hướng, không có gì cần sửa thêm ngoài các phần đã nêu ở Phase 1/2/4 của roadmap chính.

### Tổng kết điều chỉnh so với đề xuất gốc

| Hạng mục | Đề xuất gốc | Điều chỉnh sau research |
|---|---|---|
| App quét | Scaniverse hoặc Polycam | Scaniverse, export **mesh** (GLB/OBJ/FBX), không export Gaussian Splat cho mục đích collision |
| Engine vật lý (nếu đi hướng nhẹ) | PyBullet hoặc MuJoCo ngang hàng | MuJoCo (PyBullet gần như ngừng maintain) + dùng `mujoco_ros2_control` để khớp abstraction `ros2_control` toàn roadmap |
| Isaac Sim | Khuyên dùng, không nêu điều kiện | Khuyên dùng nếu GPU đạt tối thiểu RTX 4080 16GB (bản 5.1) — cần xác nhận GPU thật trước |
| License Isaac Sim | Không nhắc | Miễn phí cho R&D nội bộ kể cả giao output cho khách; chỉ trả phí nếu phân phối lại/làm dịch vụ chính Isaac Sim |
| Baking collider | Đúng ý, sai tên | Gọi đúng "Collision Approximation" (`convexDecomposition`/`sdf` cho mesh phức tạp), thêm bước dọn mesh trước khi bake |
| Vật thể robot gắp | Dùng chung pipeline scan | Vật thể cần gắp chính xác nên dùng CAD/primitive đo tay, không dùng mesh scan (sai số cm) |
| URDF Fanuc | "Chuẩn bị file URDF" (chưa rõ nguồn) | Đã có sẵn URDF chính thức cho dòng CRX trong `fanuc_driver` — chỉ cần tự vẽ nếu robot thật không phải CRX |

### Nguồn tham khảo

- [Scaniverse — Niantic's Free Mobile Gaussian Splat App](https://radiancefields.com/platforms/scaniverse)
- [What File Types Can Polycam Export? – Polycam Help Center](https://learn.poly.cam/hc/en-us/articles/27756102599572-What-File-Types-Can-Polycam-Export)
- [Is Polycam Free? Real Limits and Pricing](https://www.skyebrowse.com/news/posts/polycam-review)
- [ROS 2 Bridge in Standalone Workflow — Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/4.5.0/ros2_tutorials/tutorial_ros2_python.html)
- [Isaac Sim Requirements (5.1)](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)
- [License FAQ — Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/license-faq.html)
- [GitHub - isaac-sim/IsaacSim (Apache 2.0, open-source)](https://github.com/isaac-sim/IsaacSim)
- [pybullet - Python Package Health Analysis | Snyk](https://snyk.io/advisor/python/pybullet)
- [MuJoCo — Wikipedia](https://en.wikipedia.org/wiki/MuJoCo)
- [mujoco_ros2_control — ROS2_Control: Jazzy documentation](https://control.ros.org/jazzy/doc/mujoco_ros2_control/doc/index.html)
- [GitHub - moveit/mujoco_ros2_control](https://github.com/moveit/mujoco_ros2_control)
- [Isaac Sim collision approximation discussion (convex decomposition)](https://forums.developer.nvidia.com/t/script-for-convex-decomposition-collisions/259649)
- [FANUC ROS 2 Driver Documentation — Quick Start](https://fanuc-corporation.github.io/fanuc_driver_doc/main/docs/quick_start/quick_start.html)
- [iPhone LiDAR/photogrammetry accuracy studies (NCBI/Nature)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12473222/)
