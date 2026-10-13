# shopee-video-bot

Bot tự động: lấy video từ Google Drive → Claude viết thoại tiếng Việt (bán giải pháp) → lồng tiếng (Vbee/Azure/FPT) → che chữ gốc, chỉnh màu, phụ đề → gửi Telegram duyệt → đăng fanpage + comment link Shopee.

- Thả video vào thư mục Drive **Chờ làm**, tên file dạng `ten-bat-ky__MaLinkShopee.mp4` (vd `pancake__60SJhy1h9E.mp4` = https://s.shopee.vn/60SJhy1h9E).
- Telegram: bấm **Duyệt**, **Viết lại thoại**, **Bỏ**. Reply tin kịch bản bằng link Shopee để gắn link, hoặc bằng góp ý để viết lại theo ý.
- Lệnh: `/status`, `/help`.

Chạy trên Railway bằng Dockerfile. Biến môi trường xem `.env.example`. Cần gắn Volume vào `/data`.
