---
type: Setup Guide
title: Hướng dẫn cài đặt đầy đủ — chạy Bridge Node trên máy xưởng
project: ros2-physical-ai
created_by: Hoang Duc
created_at: 2026-09-12
status: draft — dựa trên các lệnh đã chạy thật trên simulator, PHẦN kết nối robot thật (Bước 5) chưa test thật, cần kỹ sư xưởng làm theo tài liệu fanuc_driver chính thức
---

# Hướng dẫn cài đặt — từ máy trắng tới chạy được Bridge Node

**Đọc trước**: `bridge_node` (code trong `bridge_node_source.zip`) chỉ là 1 trong 3 phần cần có. Cả 3 phần đều là source code phải tự build, không có phần nào là "thư viện cài sẵn":

| Phần | Vai trò | Nguồn | Đã build/test ở đâu |
|---|---|---|---|
| `yolo_ros` | Nhận diện vật (vision) | github.com/mgonzs13/yolo_ros, commit `eb11e81` (2026-09-05) | Đã build + chạy demo thật trên simulator |
| `fanuc_driver` + `fanuc_description` | Điều khiển tay máy (motion) | github.com/FANUC-CORPORATION, commit `a5a88ae` / `fb40c98` (2026-08-05) | Đã build + chạy `use_mock:=true` trên simulator — **CHƯA kết nối robot thật** |
| `bridge_node` | Cầu nối 2 phần trên (code của mình) | Trong `bridge_node_source.zip` kèm gói này | Đã build + test (18 unit test + 8 integration test trên simulator) |

---

## Bước 0 — Yêu cầu trước khi bắt đầu

- Máy tính/Jetson chạy **Ubuntu 24.04**.
- Robot Fanuc đã xác nhận đúng dòng CRX + controller có option Stream Motion (J519)/Remote Motion (R912)/S636 (theo ROADMAP.md Phase 5 — xưởng đã xác nhận việc này).
- Camera đã chọn và có driver ROS2 tương ứng (ví dụ USB webcam dùng `usb_cam`, hoặc camera công nghiệp có driver riêng — không nằm trong gói này, xưởng tự chọn theo phần cứng đang có).

## Bước 1 — Cài ROS 2 Jazzy

Làm theo hướng dẫn chính thức: https://docs.ros.org/en/jazzy/Installation.html (bản "Desktop Install"). Sau khi cài xong, xác nhận:
```bash
source /opt/ros/jazzy/setup.bash
ros2 doctor
```

## Bước 2 — Tạo workspace

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

## Bước 3 — Clone + build `yolo_ros` (vision)

```bash
git clone https://github.com/mgonzs13/yolo_ros.git
cd yolo_ros && git checkout eb11e81f7dbdb81c23a61d743ce0bac3cf9b07eb && cd ..
# ^ commit đã build+test cho gói này. Bỏ dòng checkout này nếu muốn dùng bản main mới nhất
#   (chưa được test lại với bridge_node ở bản mới hơn).

# Cài uv (quản lý Python dependency riêng cho package này)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # hoặc mở terminal mới để "uv" có trong PATH

cd ~/ros2_ws/src/yolo_ros/yolo_ros
uv venv --python python3 --system-site-packages .venv
uv sync --no-install-project --no-dev

cd ~/ros2_ws
rosdep update
rosdep install --from-paths src --ignore-src --filter-for-installers "apt" -r -y
```

## Bước 4 — Clone + build `fanuc_driver` (motion)

```bash
sudo apt install -y git-lfs
git lfs install

cd ~/ros2_ws/src
git clone https://github.com/FANUC-CORPORATION/fanuc_description.git
cd fanuc_description && git checkout fb40c9803a826ba68c7c8e28ba904a25efa7fcd2 && cd ..
git clone --branch main --single-branch --recurse-submodules https://github.com/FANUC-CORPORATION/fanuc_driver.git
cd fanuc_driver && git checkout a5a88aee0a44689bbe6ed8ae2e44a4f3d60060a3 && cd ..
# ^ 2 commit đã build+test cho gói này. Bỏ 2 dòng checkout này nếu muốn dùng bản main mới nhất.

cd ~/ros2_ws
rosdep install --ignore-src --from-paths src -y
```

## Bước 5 — Đặt `bridge_node` vào workspace

Giải nén `bridge_node_source.zip` (trong gói giao) vào `~/ros2_ws/src/`, sao cho có đường dẫn:
```
~/ros2_ws/src/bridge_node/package.xml
~/ros2_ws/src/bridge_node/bridge_node/*.py
...
```

## Bước 6 — Build toàn bộ workspace

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
export PATH="$HOME/.local/bin:$PATH"   # để colcon thấy "uv" khi build yolo_ros
colcon build --symlink-install --cmake-args -DBUILD_TESTING=1
source install/setup.bash
```

**Kiểm tra build không lỗi** — nếu có lỗi thiếu package apt nào, chạy lại `rosdep install --from-paths src --ignore-src -y` ở Bước 3/4 rồi build lại.

## Bước 7 — Cấu hình `bridge_node` theo số đo thật của xưởng

**Bắt buộc** trước khi launch — xem `docs/DDB-bridge-node.md` Mục 12 (Open Issues #3, #5, #6, #7) và `TEST-SCENARIO-real-robot-trial.md` Mục 2.1. Sửa các tham số khi launch (hoặc file YAML riêng), không dùng giá trị mặc định của bản test simulator:
- `workspace_bounds` — vùng an toàn thật
- `table_height` — chiều cao mặt phẳng đặt vật thật
- `camera_frame`, vị trí camera thật (cần cấu hình tf2 thật, không dùng `static_transform_publisher` giả như lúc test simulator)
- `input_camera_info_topic`, `input_detections_topic` — khớp với camera driver thật đang dùng

## Bước 8 — Launch (mỗi lệnh 1 terminal riêng, theo đúng thứ tự)

**Terminal 1 — Kết nối robot thật** (KHÔNG dùng `use_mock:=true` — cờ đó chỉ dành cho giả lập):
```bash
source ~/ros2_ws/install/setup.bash
ros2 launch fanuc_moveit_config fanuc_moveit.launch.py robot_model:=<model_thật_của_xưởng>
```
Cấu hình kết nối controller thật (IP, port...) theo [FANUC ROS 2 Driver Documentation](https://fanuc-corporation.github.io/fanuc_driver_doc/) — **phần này ngoài phạm vi gói giao**, xưởng cần làm theo tài liệu chính thức của FANUC.

**Terminal 2 — Camera thật:**
```bash
ros2 run <package_driver_camera_của_xưởng> <node_camera>
```

**Terminal 3 — Nhận diện vật:**
```bash
source ~/ros2_ws/install/setup.bash
ros2 launch yolo_bringup yolov8.launch.py input_image_topic:=<topic_ảnh_thật>
```

**Terminal 4 — Bridge Node:**
```bash
source ~/ros2_ws/install/setup.bash
ros2 launch bridge_node bridge_node.launch.py enable_on_start:=false
```
Bắt đầu với `enable_on_start:=false` (an toàn) — chỉ bật bằng `ros2 service call /bridge/enable std_srvs/srv/SetBool "{data: true}"` sau khi đã kiểm tra kỹ theo `TEST-SCENARIO-real-robot-trial.md`.

## Việc KHÔNG nằm trong gói này

- Cấu hình kết nối phần cứng Fanuc controller thật (IP/port/S636) — theo tài liệu FANUC chính thức.
- Driver cho camera cụ thể xưởng đang dùng — xưởng tự chọn/cài theo phần cứng.
- Đo và điền số liệu thật ở Bước 7 — không ai làm được thay, cần đo tại xưởng.
