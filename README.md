---
title: Video Clipper Studio
emoji: 🎬
colorFrom: red
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 🎬 Video Clipper Studio

Phiên bản **Portable Độc Lập Hoàn Toàn** — có thể copy cả thư mục `clip_studio` sang bất kỳ máy tính Windows nào (qua USB hoặc ổ cứng di động) và chạy ngay lập tức mà **không cần cài đặt Python, FFmpeg, hay Node.js**.

---

## 📦 Cấu trúc thư mục Portable
- **`VideoClipper.exe`**: File thực thi chính độc lập (~25MB), nhấp đúp là khởi động và tự động mở trình duyệt web `http://localhost:5000`.
- **`run.bat`**: Trình khởi chạy nhanh (tự động giải phóng cổng 5000 nếu bị chiếm dụng và kích hoạt `VideoClipper.exe`).
- **`bin/`**: Thư mục chứa sẵn toàn bộ bộ công cụ xử lý đa phương tiện độc lập:
  - `ffmpeg.exe` & `ffprobe.exe` (cùng toàn bộ file DLL hỗ trợ).
  - `node.exe` (JavaScript Runtime độc lập để giải mã chữ ký YouTube, bỏ qua lỗi 403).
- **`templates/` & `static/`**: Giao diện người dùng Dark Mode cao cấp (HTML, CSS, JS).
- **`outputs/`**: Thư mục kết quả — **mỗi lần cắt sẽ tự động gom vào 1 thư mục riêng** gồm:
  - File video đã cắt (`.mp4` / `.mp3`).
  - File ZIP chứa toàn bộ ảnh frame (`_frames.zip`).
  - Thư mục ảnh từng khung hình (`frames/`).

---

## 🌟 Tính năng mới được bổ sung
1. **⏱️ Cắt chính xác đến từng Mili-giây (Milliseconds)**:
   - Nhập thời gian chi tiết: `HH:MM:SS.mmm` (Ví dụ: `00:05:12.500` đến `00:05:13.750`).
   - Hai nút tinh chỉnh nhanh **`[-100ms]`** và **`[+100ms]`** ngay cạnh ô nhập giờ để nhích từng khung hình cực kỳ chuẩn xác.
2. **📁 Cách ly kết quả theo từng đợt cắt**:
   - Không bị tràn lan hay nhầm lẫn giữa các lần cắt khác nhau.
   - Nút **"📂 Mở thư mục riêng của đợt cắt này"** đưa bạn đến thẳng thư mục của lần chạy đó trên Windows Explorer.
3. **📜 Bật / Tắt theo dõi Log linh hoạt**:
   - **Cách 1 - Xem Live Logs trực tiếp trên Web**: Bấm nút **`📜 Live Logs`** ở thanh tiêu đề trên cùng để mở khung console ngầm theo dõi tiến độ thời gian thực (có nút Xoá và Sao chép log).
   - **Cách 2 - Ẩn / Hiện cửa sổ Console đen (Windows CMD)**: Bấm nút **`🖥️ Console Window`** trên góc phải để ẩn hoặc hiện cửa sổ dòng lệnh đen của Windows ngay lập tức.

---

## 🚀 Cách sử dụng
- Nhấp đúp vào **`VideoClipper.exe`** hoặc **`run.bat`**.
- Trình duyệt sẽ tự động mở trang làm việc tại `http://localhost:5000`.
