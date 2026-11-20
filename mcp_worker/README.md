# Smartoutlet MCP Worker

Cloudflare Worker làm **MCP server** (Streamable HTTP) phục vụ điều khiển Smart Power
Outlet qua MQTT. Worker chạy 24/7 trên Cloudflare nên **không phụ thuộc máy tính của
người dùng** — kể cả khi máy tắt, điện thoại vẫn gọi lệnh được.

```
Điện thoại → Gemini (app/web) → OAuth 2.1 + PKCE
                                  → HTTPS  https://<worker>.workers.dev/mcp
                                  → Worker (Cloudflare)
                                  → MQTT TCP 1883  broker.hivemq.com
                                  → topic  hoangkimvinh
                                  → ESP32-S3 / PC Agent (subscribe)
```

## 1. Yêu cầu

- Node.js 20+ (đã kiểm: v26.13.0)
- Tài khoản Cloudflare (free tier đủ)
- Broker MQTT — mặc định `broker.hivemq.com:1883`, topic `hoangkimvinh`

## 2. Cấu trúc

| File | Vai trò |
|---|---|
| `src/index.ts` | `OAuthProvider` (RFC 9728 / 8414 / 7591) + định tuyến `/mcp` |
| `src/auth.ts` | Trang `/authorize`: đăng nhập bằng mật khẩu + consent page |
| `src/tools.ts` | Định nghĩa MCP server + 3 tool |
| `src/mqtt.ts` | Client MQTT 3.1.1 tự viết trên `cloudflare:sockets` (runtime `workerd` không có `net.Socket` của Node) |
| `src/env.ts` | Kiểu `Env` + hằng số canonical (issuer, resource, scopes) |
| `wrangler.jsonc` | Bindings: `OAUTH_KV` (KV), `MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC` |
| `tsconfig.json` | Typecheck (`npm run typecheck`) |

## 3. Tool MCP

| Tool | Input | Mô tả |
|---|---|---|
| `send_command` | `command`: `on` \| `off` (bắt buộc), `note` (tùy chọn) | Publish lệnh tới topic, QoS 1, chờ PUBACK |
| `read_last_message` | `waitSeconds` 1–30, `maxMessages` 1–20 | Subscribe ngắn hạn, trả về tin nhắn nhận được |
| `server_status` | — | Broker/topic hiện tại |

Payload gửi đi (JSON):

```json
{
  "cmd": "ON",
  "note": "bật quạt tủ rack",
  "source": "mcp-worker",
  "ts": "2026-11-19T00:52:58.265Z"
}
```

## 4. Deploy

> **Instance đã deploy:** `https://smartoutlet-mcp.kimvinhh6.workers.dev`
> MCP endpoint: `https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp`

```powershell
cd mcp_worker
npm install
npx wrangler login
npx wrangler kv namespace create OAUTH_KV   # dán id vào wrangler.jsonc
npx wrangler secret put LOGIN_PASSWORD      # mật khẩu trang đăng nhập
npx wrangler secret put AUTH_SECRET         # >= 32 ký tự ngẫu nhiên, ký cookie
npx wrangler secret put MCP_TOKEN           # legacy bearer cho CLI
npm run deploy
```

## 5. Xác thực — OAuth 2.1

Gemini Web / Gemini App **không nhận** custom HTTP header; nó bắt buộc OAuth chuẩn.
Worker vì vậy chạy một authorization server OAuth 2.1 hoàn chỉnh.

| Endpoint | Chuẩn | Vai trò |
|---|---|---|
| `GET /mcp` | MCP Streamable HTTP | Endpoint MCP (cần Bearer token) |
| `GET /authorize` | — | Trang đăng nhập + consent (mở trong browser) |
| `POST /oauth/token` | RFC 6749 | Đổi code → access token, refresh token |
| `POST /oauth/register` | RFC 7591 | Dynamic Client Registration (Gemini tự đăng ký) |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 | Metadata của authorization server |
| `GET /.well-known/oauth-protected-resource/mcp` | RFC 9728 | Metadata của resource |

Cơ chế:

1. Client gọi `/mcp` **không có token** → Worker trả `401` kèm
   `WWW-Authenticate: Bearer realm="OAuth", resource_metadata="…", scope="mcp:read mcp:write"`.
2. Client đọc `resource_metadata` → biết `authorization_servers`.
3. Client đọc metadata authorization server → thấy `registration_endpoint`.
4. Client tự đăng ký (`POST /oauth/register`, public client + PKCE S256).
5. Trình duyệt mở `/authorize` → user nhập `LOGIN_PASSWORD` → bấm **Cho phép**.
6. Worker redirect về `redirect_uri` kèm `code` → client đổi code lấy token.
7. Client gọi `/mcp` với `Authorization: Bearer <access_token>`.

KV `OAUTH_KV` chứa client đã đăng ký, grant, token (chỉ băm/hash, props được mã hóa).
Token hết hạn sau 12 h, có `refresh_token` dài 30 ngày.

### Đường legacy (static Bearer)

`MCP_TOKEN` vẫn được chấp nhận ở `/mcp` cho client không chạy được OAuth (ví dụ CLI
đơn giản). Không bắt buộc, nhưng giữ lại để không gãy tài liệu cũ.

## 6. Cấu hình vào Gemini

### Gemini Web / Gemini App — `gemini.google.com`

1. Vào **Settings → Connected Apps → Custom apps**.
2. Dán MCP server URL: `https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp`.
3. Bấm **Next**. Gemini tự DCR — **không** cần nhập Client ID/Secret.
4. Trình duyệt mở `/authorize` → nhập mật khẩu → **Cho phép**.
5. Quay lại Gemini, thử: *"bật ổ cắm đi"*.

Điều kiện: tài khoản Google cá nhân, 18+, ở Mỹ, bật History/Keep Activity, giao diện
tiếng Anh. Gemini yêu cầu xác nhận thủ công cho mọi **write action**.

> Nếu Gemini báo *"Máy chủ MCP này sử dụng một phương thức xác thực mà Gemini không hỗ
> trợ"* → Worker đang chạy bản cũ (Bearer tĩnh). Deploy lại bản này.

### Antigravity CLI (`agy`)

> Gemini CLI đã bị thay bằng Antigravity CLI cho tài khoản Unpaid / Google One
> (từ 18/06/2026). Nếu bạn dùng `gemini mcp add` cũ, hãy chuyển sang `agy`.

```powershell
$env:MCP_TOKEN = "<token-cua-ban>"
agy mcp add --header "Authorization: Bearer $env:MCP_TOKEN" `
  smartoutlet https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp

agy mcp list     # phải thấy smartoutlet  enabled
```

Client khác hỗ trợ OAuth (Cursor, Claude Code) chỉ cần URL — chúng tự làm DCR:

```bash
claude mcp add --transport http smartoutlet https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp
```

Client chỉ hỗ trợ stdio thì dùng bridge `mcp-remote` — nó cũng tự làm OAuth flow.

## 7. Test

```powershell
# discovery
curl.exe https://smartoutlet-mcp.kimvinhh6.workers.dev/.well-known/oauth-authorization-server
curl.exe https://smartoutlet-mcp.kimvinhh6.workers.dev/.well-known/oauth-protected-resource/mcp

# 401 challenge
curl.exe -i https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp

# dynamic client registration
curl.exe -X POST https://smartoutlet-mcp.kimvinhh6.workers.dev/oauth/register `
  -H "content-type: application/json" `
  --data-binary "@dcr.json"

# tools/call qua legacy bearer -> publish ON
curl.exe -X POST https://smartoutlet-mcp.kimvinhh6.workers.dev/mcp `
  -H "Authorization: Bearer $env:MCP_TOKEN" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  --data-binary "@call.json"
```

E2E đầy đủ (DCR → login → consent → code → token → refresh → tool call):
`../.work/oauth_e2e.py`.

Kiểm tra độc lập (subscriber Python, không qua Worker):

```powershell
python ..\.work\mqtt_sub.py hoangkimvinh 30
```

## 8. Local dev

```powershell
npm run dev          # http://127.0.0.1:8787/mcp
```

`wrangler dev` chạy runtime `workerd` thật nên `cloudflare:sockets` hoạt động giống
production. Cần set secret cho local:

```powershell
$env:MCP_TOKEN="devtoken"
$env:LOGIN_PASSWORD="devpass"
$env:AUTH_SECRET="dev-secret-at-least-32-characters-long"
npx wrangler dev
```

## 9. Ràng buộc đã biết

- `cloudflare:sockets` chỉ chặn port 25 và dải IP của Cloudflare → port 1883 OK.
- Mỗi lần gọi tool là 1 kết nối TCP mới tới broker (Worker không giữ connection
  giữa các request). Đủ dùng cho lệnh điều khiển, không phù hợp telemetry cao tần.
- Broker `broker.hivemq.com` public không có TLS ở port 1883 → **không** dùng
  username/password có giá trị thật. Topic hiện tại là public.
- Topic `hoangkimvinh` không có tiền tố namespace — nên đổi sang
  `smartoutlet/rack/rack-01/cmd` khi tích hợp ESP32 (xem `docs/PLAN_GR2.md` A-10).
- Authorization server **không phải** identity provider: đăng nhập bằng một mật khẩu
  dùng chung. Đủ cho dùng cá nhân, không phù hợp nhiều người dùng.
