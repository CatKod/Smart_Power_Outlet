# STATE — Smart Power Outlet

> Cập nhật: 2026-11-17 · Nhánh: `feature/gr2-pc-agent-service`

## Slice hiện tại — Giai đoạn 1 GR2 Tuần 2 (đóng) + báo cáo

| Việc | Trạng thái |
|---|---|
| Cập nhật `ROADMAP.md` (Track E, Track D, header) | ✅ |
| Sinh `docs/reports/report_week2.docx` | ✅ |
| Cập nhật `README.md` (tài liệu + mục thư viện) | ✅ |
| `.gitignore` bỏ qua file lock Word (`~$*`) | ✅ |

### Verify đã chạy
- `python -m pytest tests -q` → **36 passed** (pc_agent)
- `arduino-lint --compliance strict --library-manager submit` → 0 ERROR
- ESP-IDF build từ registry (target `esp32s3`) → exit 0, `dependencies.lock` xác nhận `source: {type: service}`
- CI thư viện: 4/4 job xanh (run `43797621114`)
- docx: 137 paragraph, 30 table, 15 Heading 1, 29 Heading 2 — đọc lại bằng python-docx
- Link trong `README.md` + `ROADMAP.md` → tất cả tồn tại

## Bằng chứng thư viện `embedded-iot-toolkit` v1.0.0

- Arduino: PR `arduino/library-registry#9655` — MERGED 2026-11-16 02:45 UTC
- ESP-IDF: https://components.espressif.com/components/catkod/embedded-iot-toolkit/versions/1.0.0
- Repo: https://github.com/CatKod/embedded-iot-toolkit

## Sai lệch đã phát hiện & đã sửa trong lúc làm

1. **Claim sai về soak 24 h** — đã viết "A-6-6 đóng" vào ROADMAP nhưng **không có bằng chứng** soak 24 h đã chạy (chỉ có lần chạy 45 s trong ghi chú 2026-11-15). Đã sửa lại thành "phần mềm xong, còn lại chạy 24 h thật".
2. **Bảng 8.1 trong báo cáo** — mô tả nhóm test không tồn tại trong `pc_agent/tests/`. Đã viết lại theo đúng 36 test thực tế từ `pytest --collect-only`.
3. **Tổng số test lệch** (40 vs 36) sau khi sửa lần đầu → đã đối chiếu lại và đưa về 36.

## Task còn lại (Giai đoạn 2 — cần phần cứng)

`A-4-8`, `A-4-9`, `A-7-5`, `A-9-5`, `A-9-6`, `A-5-4`, `A-6-6` (chạy 24 h thật).
Chuẩn bị môi trường: `docs/operations/HARDWARE_PREP.md`.

## Ghi chú vận hành

- Token ESP registry (`write:components`) lưu plaintext tại `D:\ProgramData\Espressif\idf_component_manager.yml` — **không commit**, nên revoke sau khi xong series publish.
