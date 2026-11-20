/**
 * Interactive authorization endpoint for the Smart Power Outlet OAuth server.
 *
 * Gemini (web / mobile / CLI) opens /authorize in a browser, signs in here,
 * approves the client, and is redirected back with an authorization code.
 *
 * The sign-in step is a single shared password (LOGIN_PASSWORD). The session
 * cookie is signed with AUTH_SECRET, so no server-side session store is needed.
 */

import {
  AuthorizationError,
  CimdFetchError,
  type OAuthHelpers,
} from "@cloudflare/workers-oauth-provider";

import { SCOPES_SUPPORTED, type Env } from "./env";

const SESSION_COOKIE = "__Host-smartoutlet-session";
const SESSION_TTL_SECONDS = 60 * 60 * 12;
const USER_ID = "owner";

/* ------------------------------------------------------------------ */
/* session cookie                                                      */
/* ------------------------------------------------------------------ */

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function signValue(value: string, secret: string): Promise<string> {
  const key = await hmacKey(secret);
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(value),
  );
  return `${value}.${toBase64Url(new Uint8Array(signature))}`;
}

async function verifyValue(
  signed: string | undefined,
  secret: string,
): Promise<string | null> {
  if (!signed) return null;
  const index = signed.lastIndexOf(".");
  if (index <= 0) return null;
  const value = signed.slice(0, index);
  const signature = signed.slice(index + 1);
  const key = await hmacKey(secret);
  let ok = false;
  try {
    ok = await crypto.subtle.verify(
      "HMAC",
      key,
      base64UrlToBytes(signature),
      new TextEncoder().encode(value),
    );
  } catch {
    return null;
  }
  return ok ? value : null;
}

function base64UrlToBytes(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function readCookie(request: Request, name: string): string | undefined {
  const header = request.headers.get("cookie") ?? "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

async function isSignedIn(request: Request, env: Env): Promise<boolean> {
  if (!env.AUTH_SECRET) return false;
  const raw = await verifyValue(readCookie(request, SESSION_COOKIE), env.AUTH_SECRET);
  if (!raw) return false;
  const [userId, expiresAt] = raw.split("|");
  if (!userId) return false;
  if (expiresAt && Number(expiresAt) < Date.now()) return false;
  return true;
}

function sessionCookie(value: string, maxAge: number): string {
  return `${SESSION_COOKIE}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
}

function expiredSessionCookie(): string {
  return `${SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;
}

/* ------------------------------------------------------------------ */
/* html helpers                                                        */
/* ------------------------------------------------------------------ */

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (char) => `&#${char.charCodeAt(0)};`,
  );
}

const PAGE_STYLE = `
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         background: #0f1115; color: #e6e8eb; margin: 0;
         display: flex; min-height: 100vh; align-items: center; justify-content: center; }
  .card { background: #181b21; border: 1px solid #2a2f38; border-radius: 14px;
          padding: 28px 32px; max-width: 480px; width: 92%; }
  h1 { font-size: 19px; margin: 0 0 14px; }
  p { line-height: 1.55; font-size: 14px; color: #b6bcc6; }
  ul { padding-left: 18px; font-size: 13px; color: #b6bcc6; }
  label { display: block; font-size: 13px; margin: 10px 0; }
  input[type=password] { width: 100%; padding: 10px 12px; margin-top: 6px;
                         border-radius: 8px; border: 1px solid #2f3540;
                         background: #10131a; color: #e6e8eb; font-size: 14px; }
  button { margin-top: 14px; margin-right: 8px; padding: 10px 18px; border-radius: 8px;
           border: 0; font-size: 14px; cursor: pointer; }
  .allow { background: #3b82f6; color: #fff; }
  .deny { background: #2a2f38; color: #cfd4dc; }
  .warn { background: #2a2118; border: 1px solid #5c4526; border-radius: 8px;
          padding: 10px 12px; font-size: 13px; color: #e8c89a; }
  .error { background: #2a181b; border: 1px solid #5c2630; border-radius: 8px;
           padding: 10px 12px; font-size: 13px; color: #f0a5b2; }
  code { background: #10131a; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
`;

function page(title: string, body: string): string {
  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${escapeHtml(title)}</title>
<style>${PAGE_STYLE}</style>
</head>
<body>
<div class="card">
${body}
</div>
</body>
</html>`;
}

function htmlResponse(html: string, status = 200, extraHeaders?: Headers): Response {
  const headers = new Headers(extraHeaders);
  headers.set("content-type", "text/html; charset=utf-8");
  headers.set("cache-control", "no-store");
  headers.set("x-frame-options", "DENY");
  headers.set("content-security-policy", "frame-ancestors 'none'");
  return new Response(html, { status, headers });
}

/* ------------------------------------------------------------------ */
/* authorize handler                                                   */
/* ------------------------------------------------------------------ */

export async function handleAuthorize(
  request: Request,
  env: Env,
  oauth: OAuthHelpers,
): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === "GET") {
    if (!(await isSignedIn(request, env))) {
      return htmlResponse(
        page(
          "Đăng nhập - Smart Power Outlet",
          `<h1>Smart Power Outlet</h1>
           <p>Nhập mật khẩu để cấp quyền truy cập ổ cắm thông minh.</p>
           <form method="post" action="/authorize">
             <input type="hidden" name="action" value="login">
             <input type="hidden" name="query" value="${escapeHtml(url.search)}">
             <label>Mật khẩu
               <input type="password" name="password" autocomplete="current-password" required autofocus>
             </label>
             <button class="allow" type="submit">Đăng nhập</button>
           </form>`,
        ),
      );
    }

    try {
      const authRequest = await oauth.parseAuthRequest(request);
      const details = await oauth.describeConsent(authRequest);
      const consent = await oauth.beginConsent(authRequest);
      const scopeList = details.scope.length
        ? details.scope
            .map((scope) => `<li><code>${escapeHtml(scope)}</code></li>`)
            .join("")
        : "<li>Không có scope cụ thể (đọc và ghi lệnh).</li>";

      return htmlResponse(
        page(
          `Cấp quyền cho ${details.clientName}`,
          `<h1>Cho phép ${escapeHtml(details.clientName)}?</h1>
           <p>${
             details.clientDomain
               ? `Ứng dụng được phát hành bởi <strong>${escapeHtml(details.clientDomain)}</strong>.`
               : "Ứng dụng này tự đăng ký, tên của nó không được xác minh."
           }
           Token sẽ được gửi tới <strong>${escapeHtml(details.redirectHost)}</strong>.</p>
           ${
             details.redirectIsLoopback
               ? `<p class="warn">Token sẽ được gửi tới một ứng dụng chạy trên máy tính của bạn. Chỉ tiếp tục nếu bạn vừa tự mở nó.</p>`
               : ""
           }
           <p>Ứng dụng muốn truy cập:</p>
           <ul>${scopeList}</ul>
           <form method="post" action="/authorize">
             <input type="hidden" name="handle" value="${escapeHtml(consent.handle)}">
             <button class="allow" name="decision" value="approve" type="submit">Cho phép</button>
             <button class="deny" name="decision" value="deny" type="submit">Từ chối</button>
           </form>`,
        ),
        200,
        consent.headers,
      );
    } catch (error) {
      return renderAuthorizationError(error);
    }
  }

  if (request.method === "POST") {
    const form = await request.formData();
    const action = String(form.get("action") ?? "");

    if (action === "login") {
      const password = String(form.get("password") ?? "");
      if (!env.LOGIN_PASSWORD || password !== env.LOGIN_PASSWORD) {
        return htmlResponse(
          page(
            "Đăng nhập - Smart Power Outlet",
            `<h1>Smart Power Outlet</h1>
             <p class="error">Mật khẩu không đúng.</p>
             <form method="post" action="/authorize">
               <input type="hidden" name="action" value="login">
               <input type="hidden" name="query" value="${escapeHtml(String(form.get("query") ?? ""))}">
               <label>Mật khẩu
                 <input type="password" name="password" autocomplete="current-password" required autofocus>
               </label>
               <button class="allow" type="submit">Đăng nhập</button>
             </form>`,
          ),
        );
      }

      const expiresAt = Date.now() + SESSION_TTL_SECONDS * 1000;
      const signed = await signValue(`${USER_ID}|${expiresAt}`, env.AUTH_SECRET);
      const rawQuery = String(form.get("query") ?? "");
      const query = rawQuery.startsWith("?") ? rawQuery.slice(1) : rawQuery;
      const location = query ? `/authorize?${query}` : "/authorize";
      return new Response(null, {
        status: 302,
        headers: {
          location,
          "set-cookie": sessionCookie(signed, SESSION_TTL_SECONDS),
          "cache-control": "no-store",
        },
      });
    }

    if (!(await isSignedIn(request, env))) {
      return htmlResponse(
        page(
          "Phiên hết hạn - Smart Power Outlet",
          `<h1>Phiên đăng nhập đã hết hạn</h1>
           <p>Vui lòng đăng nhập lại rồi thử cấp quyền.</p>
           <p><a href="/authorize${escapeHtml(url.search)}">Đăng nhập lại</a></p>`,
        ),
        401,
      );
    }

    const handle = String(form.get("handle") ?? "");
    try {
      if (form.get("decision") !== "approve") {
        const denied = await oauth.denyConsent(request, handle);
        return new Response(null, {
          status: 302,
          headers: denied.headers,
        });
      }

      // Approve without narrowing the scope: the client keeps exactly what it
      // asked for. Google asks for its own scope names, and rejecting them
      // here would break the flow before the token is ever issued.
      const approved = await oauth.approveConsent(request, handle);
      const { redirectTo } = await oauth.completeAuthorization({
        request: approved.request,
        userId: USER_ID,
        metadata: {},
        scope: approved.request.scope,
        props: { userId: USER_ID },
      });
      approved.headers.set("location", redirectTo);
      return new Response(null, { status: 302, headers: approved.headers });
    } catch (error) {
      return renderAuthorizationError(error);
    }
  }

  return htmlResponse(
    page(
      "Phương thức không hỗ trợ",
      `<h1>Phương thức không hỗ trợ</h1><p>${escapeHtml(request.method)}</p>`,
    ),
    405,
  );
}

function renderAuthorizationError(error: unknown): Response {
  if (error instanceof AuthorizationError) {
    // Only redirect when the client and its redirect URI were already validated.
    if (error.redirectUri) {
      const redirect = new URL(error.redirectUri);
      redirect.searchParams.set("error", error.code);
      if (error.description) {
        redirect.searchParams.set("error_description", error.description);
      }
      if (error.state) redirect.searchParams.set("state", error.state);
      if (error.issuer) redirect.searchParams.set("iss", error.issuer);
      return new Response(null, { status: 302, headers: { location: redirect.href } });
    }
    return htmlResponse(
      page(
        "Yêu cầu không hợp lệ",
        `<h1>Yêu cầu không hợp lệ</h1>
         <p class="error">${escapeHtml(error.description)}</p>
         <p>Hãy bắt đầu lại từ đầu.</p>`,
      ),
      400,
    );
  }

  if (error instanceof CimdFetchError) {
    return htmlResponse(
      page(
        "Không xác minh được ứng dụng",
        `<h1>Không xác minh được ứng dụng</h1>
         <p class="error">Tài liệu metadata của client không tải hoặc không hợp lệ.</p>`,
      ),
      400,
    );
  }

  console.error("OAuth authorize error", error);
  return htmlResponse(
    page(
      "Lỗi máy chủ",
      `<h1>Lỗi máy chủ</h1><p>Đã xảy ra lỗi không mong muốn.</p>`,
    ),
    500,
  );
}

/** Scopes this server can grant, for the metadata documents. */
export { expiredSessionCookie };
