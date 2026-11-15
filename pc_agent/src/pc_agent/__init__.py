"""PC Agent — Electronic PC Agent cho hệ thống Smart Power Outlet.

Chạy headless 24/7 trên máy chủ (Windows Service hoặc Linux systemd daemon):
tự dò cổng serial, xác minh PZEM-004T bằng Modbus-RTU, lấy mẫu liên tục,
lưu lịch sử vào SQLite và phục vụ API đọc số liệu.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
