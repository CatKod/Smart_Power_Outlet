"""Driver thiết bị đo điện.

Mỗi driver đặc thể thiết bị sở hữu bảng thanh ghi và quy tắc giải mã riêng,
nhưng **không** tự quản lý vòng đời cổng serial — việc đó thuộc về
`pc_agent.core.poller`.
"""

from .pzem004t import Pzem004T, PzemError, PzemMetrics  # noqa: F401

__all__ = ["Pzem004T", "PzemError", "PzemMetrics"]
