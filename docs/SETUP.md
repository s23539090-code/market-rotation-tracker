# Hướng dẫn cài đặt (không cần biết code)

Hướng dẫn này giả định bạn đã có tài khoản GitHub `s23539090-code` (Okada
Research) và một file `.zip` chứa toàn bộ dự án.

## Bước 1 — Tạo repo trên GitHub

1. Đăng nhập GitHub bằng tài khoản `s23539090-code`.
2. Vào [github.com/new](https://github.com/new).
3. Đặt tên repo: `market-rotation-tracker`.
4. Chọn **Public** (để CoinGecko và người đọc bài có thể xem).
5. **Không** tick "Add a README file" (mình đã có sẵn).
6. Bấm **Create repository**.

## Bước 2 — Tải code lên

1. Giải nén file `.zip` bạn nhận được ra máy.
2. Trên trang repo vừa tạo, bấm **uploading an existing file** (hoặc **Add
   file → Upload files**).
3. Mở thư mục đã giải nén, **chọn tất cả file và thư mục bên trong** (không
   chọn thư mục cha), rồi kéo thả toàn bộ vào khung upload của GitHub.
   GitHub sẽ tự giữ đúng cấu trúc thư mục con.
4. Cuộn xuống, bấm **Commit changes**.
5. Kiểm tra lại: repo phải có các thư mục `rotation/`, `config/`, `docs/`,
   `.github/workflows/`, và file `run.py`, `README.md`.

> Lưu ý: tuyệt đối không upload file `.env` nếu bạn lỡ tạo nó trên máy —
> file này chứa API key và không nên xuất hiện công khai.

## Bước 3 — Thêm API key vào GitHub (an toàn, không ai xem được)

1. Vào tab **Settings** của repo (không phải Settings tài khoản).
2. Menu bên trái: **Secrets and variables → Actions**.
3. Bấm **New repository secret**.
4. Name: `COINGECKO_API_KEY` — Value: dán key bạn tạo sau khi được Brian
   nâng cấp. Bấm **Add secret**.
5. (Tùy chọn) Nếu bạn dùng key Demo miễn phí thay vì key trả phí, thêm thêm
   một secret: Name `COINGECKO_ENVIRONMENT`, Value `demo`.

## Bước 4 — Bật chạy tự động mỗi giờ

Workflow đã có sẵn trong `.github/workflows/hourly.yml`, không cần làm gì
thêm — nó sẽ tự chạy mỗi giờ một lần sau khi bạn upload xong.

Để chạy thử ngay (không cần đợi đến giờ):
1. Vào tab **Actions** của repo.
2. Bấm vào workflow **"Hourly rotation snapshot"** ở danh sách bên trái.
3. Bấm nút **Run workflow** (góc phải) → **Run workflow** lần nữa để xác
   nhận.
4. Đợi khoảng 1 phút, refresh trang — nếu có dấu tích xanh ✅ là chạy thành
   công. Nếu có dấu X đỏ, bấm vào để xem log lỗi (thường là do key sai hoặc
   `COINGECKO_ENVIRONMENT` không khớp loại key).

## Bước 5 — Bật GitHub Pages (để có link dashboard công khai)

1. Vào **Settings → Pages**.
2. Mục **Source**: chọn **Deploy from a branch**.
3. Mục **Branch**: chọn `main`, thư mục chọn **/docs**, bấm **Save**.
4. Đợi 1–2 phút, GitHub sẽ hiện link dạng:
   `https://s23539090-code.github.io/market-rotation-tracker/`
5. Mở link đó — đây chính là link dashboard để đưa vào bài X Article và
   video.

## Sau khi xong

- Dashboard sẽ tự cập nhật mỗi giờ, không cần bạn làm gì thêm.
- Muốn đổi sector theo dõi hoặc trọng số điểm số: sửa file
  `config/sectors.json` ngay trên GitHub (bấm vào file → biểu tượng bút chì
  → sửa → Commit changes).
- Nếu workflow báo lỗi liên tục, chụp màn hình log lỗi (phần **Actions** →
  workflow bị đỏ → bấm vào step bị lỗi) và gửi lại để được hỗ trợ — log
  không bao giờ in ra API key thật.
