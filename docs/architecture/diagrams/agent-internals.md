# Kiến trúc nội bộ Electronic PC Agent

Tài liệu này mô tả chi tiết các thành phần bên trong, luồng xử lý và vòng đời hoạt động của **Electronic PC Agent** (chạy dưới dạng Windows Service `SmartPowerOutletAgent` hoặc Linux systemd daemon `smart-power-agent.service`).

---

## 1. Sơ đồ luồng xử lý nội bộ (Mermaid Flowchart)

```mermaid
flowchart TD
    PZEM["Phan cung PZEM-004T V3.0<br/>(Dien 1 pha 220V AC)"]

    subgraph DiscoveryBranch["COM Auto-Discovery & Anti-Flapping Cache"]
        direction TB
        CacheFile["File cau hinh<br/>%ProgramData%\\SmartPowerOutlet\\config.json"]
        Tier1["Bac 1: Fast-path cong COM da nho"]
        Tier2["Bac 2: Uu tien theo duong dan USB vat ly"]
        Tier3["Bac 3: Quet cong USB-TTL o dia chi uu tien"]
        Tier4["Bac 4: Quet toan bo dai slave 0x01..0xF7"]
        Verify["Xac minh thiet bi that<br/>(Frame dung + CRC dung + U/f hop ly)"]
        UpdateCache["Anti-Flapping Cache<br/>(Chi ghi de khi da xac minh)"]

        CacheFile --> Tier1
        Tier1 -->|Khong tim thay| Tier2
        Tier2 -->|Khong tim thay| Tier3
        Tier3 -->|Khong tim thay| Tier4
        Tier1 -->|Tim thay| Verify
        Tier2 -->|Tim thay| Verify
        Tier3 -->|Tim thay| Verify
        Tier4 -->|Tim thay| Verify
        Verify -->|Thanh cong| UpdateCache
        UpdateCache -->|Luu cong hop le| CacheFile
    end

    subgraph CoreEngine["Modbus Engine & In-process Poller"]
        direction TB
        ModbusEngine["Modbus-RTU Engine<br/>(9600 8N1, FC 0x04, doc 10 input registers)"]
        Poller["Poller chu ky 1 Hz<br/>(Thuc thi doc lien tuc 24/7)"]
        InMemoryState["In-memory Current State<br/>(Metrics tuc thoi)"]

        ModbusEngine --> Poller
        Poller --> InMemoryState
    end

    subgraph RuleAndStore["Rule Engine & SQLite WAL Store"]
        direction TB
        RuleEngine["Rule Engine (In-process)<br/>- Qua cong suat<br/>- Qua dien ap / Sut ap<br/>- Canh bao tich hop PZEM<br/>- Thiet bi offline"]
        
        subgraph SQLiteDB["SQLite WAL Time-series Store"]
            TableRaw[("telemetry_raw<br/>Giu 14 ngay")]
            TableHourly[("telemetry_hourly<br/>Giu 365 ngay")]
            TableEvents[("events<br/>Lich su su kien")]
        end

        RuleEngine -->|Ghi nhan canh bao| TableEvents
        TableRaw -->|Tong hop dinh ky| TableHourly
    end

    subgraph Interfaces["Giao tiep ngoai (APIs & MQTT)"]
        direction TB
        RestServer["REST API Server (http.server chuan Python)<br/>Bind: 127.0.0.1:8000 | Auth: Bearer token tuy chon<br/>Endpoints:<br/>/ , /api/health , /api/status<br/>/api/metrics , /api/history<br/>/api/events , /api/config"]
        MqttClient["MQTT Client (Giai doan sau - dang tat)<br/>Topic: smartoutlet/rack/rack_id/meter/meter_id"]
    end

    UpdateCache -->|Thiet lap cong COM| ModbusEngine
    PZEM <-->|"Giao thuc Modbus-RTU qua \\\\.\\COMx"| ModbusEngine
    Poller -->|Moi chu ky 1s| RuleEngine
    Poller -->|Ghi du lieu goc 1 Hz| TableRaw
    InMemoryState -->|Du lieu hien tai| RestServer
    SQLiteDB -->|Lich su & su kien| RestServer
    InMemoryState -.->|Publish du lieu goc| MqttClient
```

---

## 2. Vòng đời Windows Service (Mermaid stateDiagram-v2)

Dịch vụ chạy dưới tên định danh `SmartPowerOutletAgent` (tên hiển thị: "Smart Power Outlet PC Agent") với cơ chế tự động phục hồi bởi Service Control Manager (SCM).

```mermaid
stateDiagram-v2
    [*] --> Stopped: Dang ky / Cai dat Windows Service

    Stopped --> StartPending: SCM goi StartService / OS khoi dong
    
    state StartPending {
        [*] --> LoadConfig: Doc config.json
        LoadConfig --> InitDiscovery: Khoi dong COM Auto-Discovery
        InitDiscovery --> OpenDB: Mo ket noi SQLite WAL
        OpenDB --> StartAPI: Khoi chay REST API 127.0.0.1:8000
        StartAPI --> [*]: Khoi tao hoan tat
    }

    StartPending --> Running: Bao Service RUNNING ve SCM
    
    state Running {
        [*] --> ModbusPolling: Vong lap doc chu ky 1 Hz
        ModbusPolling --> RuleEvaluation: Kiem tra nguong canh bao
        RuleEvaluation --> StoreData: Ghi vao telemetry_raw
        StoreData --> ServeAPI: San sang phuc vu REST request
        ServeAPI --> ModbusPolling
    }

    Running --> StopPending: SCM gui lenh SERVICE_CONTROL_STOP / Shutdown
    
    state StopPending {
        [*] --> StopPoller: Dung vong lap 1 Hz
        StopPoller --> CloseSerial: Dong cong COM
        CloseSerial --> CheckpointWAL: SQLite checkpoint & dong DB
        CheckpointWAL --> StopAPI: Dong HTTP server
        StopAPI --> [*]: Giai phong hoan tat
    }

    StopPending --> Stopped: Bao Service STOPPED ve SCM
    
    Running --> ServiceFailure: Tien trinh crash / Unhandled Exception
    ServiceFailure --> Stopped: SCM ghi nhan tien trinh dot ngot ket thuc
    Stopped --> StartPending: SCM Auto-restart (Che do Recovery sau 5s/10s)

    Stopped --> [*]: Go bo service (sc delete)
```

---

## 3. Bảng luồng dữ liệu (Data Flows)

| Nguồn | Đích | Giao thức | Tần suất |
| :--- | :--- | :--- | :--- |
| **PZEM-004T V3.0** | **Modbus-RTU Engine** | Modbus-RTU qua serial `\\.\COMx` (9600 baud, 8N1, Function Code 0x04, đọc 10 input registers) | 1 Hz (1 lần mỗi giây) |
| **COM Auto-Discovery** | **Anti-Flapping Cache** | Ghi đè file JSON cục bộ (`%ProgramData%\SmartPowerOutlet\config.json`) | Khi khởi động hoặc khi cổng COM thay đổi và đã xác minh thành công thiết bị thật |
| **Modbus-RTU Engine** | **In-memory Current State** | Bộ nhớ nội bộ tiến trình (in-process memory update) | 1 Hz (ngay sau khi nhận frame Modbus hợp lệ) |
| **Poller** | **Rule Engine (In-process)** | Hàm gọi nội bộ (in-memory function call) | 1 Hz (sau mỗi lần đọc dữ liệu mới) |
| **Poller** | **Bảng `telemetry_raw` (SQLite WAL)** | SQLite INSERT (Chế độ WAL mode) | 1 Hz (lưu trữ đầy đủ dữ liệu trong 14 ngày) |
| **Bộ tổng hợp (Aggregator)** | **Bảng `telemetry_hourly` (SQLite WAL)** | SQLite INSERT / SELECT aggregate | 1 giờ / lần (lưu trữ dữ liệu trung bình trong 365 ngày) |
| **Rule Engine** | **Bảng `events` (SQLite WAL)** | SQLite INSERT | Tức thời khi phát hiện vượt ngưỡng hoặc thiết bị offline |
| **Bên ngoài (Dashboard / Web / Client)** | **REST API (`http.server`)** | HTTP / JSON tại `127.0.0.1:8000` (Hỗ trợ Bearer Token tùy chọn) | Bất đồng bộ theo yêu cầu (on-demand polling từ UI / scripts) |
| **In-memory Current State** | **MQTT Broker** *(Giai đoạn sau)* | MQTT (Topic `smartoutlet/rack/<rack_id>/meter/<meter_id>`) | 1 Hz hoặc theo sự kiện *(Hiện tại đang tắt)* |
