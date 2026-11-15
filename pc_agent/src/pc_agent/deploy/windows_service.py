"""Wrapper Windows Service cho PC Agent (dựa trên `pywin32`).

Vì sao `pywin32` thay vì WinSW / NSSM?

  - **Không cần binary ngoài**: cài đặt chỉ cần `pip install pywin32`; không
    phải tải `WinSW-x64.exe` (15–18 MB) hay `nssm.exe` (mà EDR/Defender hay
    gắn cờ "HackTool" — NSSM đã không phát hành từ 2014).
  - **Chạy được với `venv`**: xem phần "Vì sao không dùng pythonservice.exe".
  - **Cấu hình đủ dùng**: `win32serviceutil.HandleCommandLine` hỗ trợ
    `--startup=delayed` (tự khởi động trễ sau khi hệ thống ổn định) và
    `--username/--password` (chạy dưới tài khoản riêng).
  - **Giữ được ưu điểm của wrapper ngoài**: vẫn tự cấu hình `FailureActions`
    để SCM tự khởi động lại service khi tiến trình chết.

Vì sao KHÔNG dùng `pythonservice.exe` (wrapper mặc định của pywin32)?

`pythonservice.exe` được **link cứng** với `pythonXY.dll` của bản Python gốc
(mã nguồn: `win32/src/PythonService.cpp` — `PyService_InitializeWithProgramName`
→ `Py_InitializeFromConfig` đọc `PythonCore` trong registry). Nó **không** đọc
`pyvenv.cfg`, nên:

  - service sẽ chạy bằng Python gốc, không phải bản trong `venv` → mất
    `pyserial` đã cài trong venv;
  - `pythonservice.exe` được `LocatePythonServiceExe()` chép vào `sys.exec_prefix`
    (thư mục venv), nhưng `pythonXY.dll` nằm ở thư mục cài đặt gốc → không
    nạp được DLL → service không chạy.

Pywin32 hỗ trợ cách khác: **`python.exe` trực tiếp làm host** (chính comment
trong `PythonService.cpp` ghi: *"it is now possible for python.exe to directly
host services"*). Ta làm đúng vậy:

    ImagePath = "<venv>\\Scripts\\python.exe" "<...>\\windows_service.py"

Khi SCM khởi động, tiến trình chạy script này với **không tham số nào**, ta
gọi `servicemanager.Initialize()` → `PrepareToHostSingle(cls)` →
`StartServiceCtrlDispatcher()`; SCM gọi ngược `SvcDoRun()`.

Cài đặt:

    python windows_service.py --startup=delayed install
    python windows_service.py start

Xem `deploy/install_service.ps1` cho kịch bản đầy đủ.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Cho phép chạy trực tiếp từ thư mục này mà không cần cài package.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pc_agent.__main__ import AgentRuntime  # noqa: E402
from pc_agent.config import ConfigStore, log_dir  # noqa: E402
from pc_agent.logging_setup import setup_logging  # noqa: E402

LOG = logging.getLogger("pc_agent.service")

SERVICE_NAME = "SmartPowerOutletAgent"
SERVICE_DISPLAY_NAME = "Smart Power Outlet PC Agent"
SERVICE_DESCRIPTION = (
    "Electronic PC Agent - doc va giam sat nang luong PZEM-004T (Modbus-RTU) "
    "cho he thong Smart Power Outlet. Chay 24/7, khong can dang nhap."
)

# Lỗi SCM trả về khi tiến trình không được SCM khởi chạy.
ERROR_FAILED_SERVICE_CONTROLLER_CONNECT = 1063


# --------------------------------------------------------------------------- #
# Lớp service — chỉ tồn tại trên Windows
# --------------------------------------------------------------------------- #
if os.name == "nt":
    import win32event
    import win32service
    import win32serviceutil

    class SmartPowerOutletAgentService(win32serviceutil.ServiceFramework):
        """Service Windows do PC Agent đảm nhiệm.

        Lớp này **phải nằm ở cấp module** (không bọc trong hàm): khi SCM
        khởi động, `servicemanager` nạp lại module này và tìm lớp service bằng
        tên thuộc tính `__module__` + tên lớp.
        """

        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        # ImagePath của service: dùng Python của **venv** đang chạy lệnh cài
        # đặt, chứ không dùng `pythonservice.exe` (xem module docstring).
        _exe_name_ = sys.executable
        _exe_args_ = f'"{Path(__file__).resolve()}"'

        def __init__(self, args):
            super().__init__(args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.runtime: Optional[AgentRuntime] = None

        # -- vòng đời SCM ---------------------------------------------- #
        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            LOG.info("SCM yêu cầu dừng service.")
            if self.runtime is not None:
                self.runtime.stop()
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            import servicemanager

            try:
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, ""),
                )
            except Exception:  # noqa: BLE001 - event log không bắt buộc
                pass

            setup_logging(log_dir(), console=False)

            store = ConfigStore()
            config = store.load()
            self.runtime = AgentRuntime(config, store)

            try:
                self.runtime.start()
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                LOG.info(
                    "PC Agent service đã khởi động | meter=%s | API=%s:%d",
                    config.meter_id, config.api_host, config.api_port,
                )
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
            except Exception:  # noqa: BLE001
                LOG.exception("Service gặp lỗi nghiêm trọng.")
            finally:
                if self.runtime is not None:
                    self.runtime.stop()
                    self.runtime = None
                try:
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_STOPPED,
                        (self._svc_name_, ""),
                    )
                except Exception:  # noqa: BLE001
                    pass

else:  # pragma: no cover - chỉ để module import được trên Linux
    SmartPowerOutletAgentService = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Chạy
# --------------------------------------------------------------------------- #
def run_as_service() -> int:
    """Chế độ service: để SCM điều khiển vòng đời.

    Đây là điểm vào được SCM gọi (ImagePath trỏ thẳng vào script này).
    """
    import servicemanager

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(SmartPowerOutletAgentService)
    try:
        servicemanager.StartServiceCtrlDispatcher()
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
        if code == ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
            # Không phải do SCM khởi chạy (chạy tay để debug) → chạy foreground.
            print(
                "Chưa được SCM khởi chạy — chuyển sang chế độ foreground.\n"
                "Dùng 'python -m pc_agent' để chạy foreground có log console.",
                file=sys.stderr,
            )
            return _run_foreground()
        raise
    return 0


def _run_foreground() -> int:
    """Chạy agent ở chế độ foreground (tiện khi debug, không cần SCM)."""
    from pc_agent.__main__ import run_agent

    return run_agent(console=True)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if os.name != "nt":
        print(
            "File này chỉ dùng trên Windows. Trên Linux hãy dùng systemd unit "
            "trong pc_agent/deploy/smart-power-agent.service.",
            file=sys.stderr,
        )
        return 1

    try:
        import win32serviceutil
    except ImportError:
        print("Thiếu pywin32. Cài bằng: pip install pywin32", file=sys.stderr)
        return 1

    # Không có tham số → SCM khởi chạy service.
    if len(argv) == 1:
        return run_as_service()

    # Có tham số → chế độ dòng lệnh: install / remove / start / stop / ...
    win32serviceutil.HandleCommandLine(SmartPowerOutletAgentService)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
