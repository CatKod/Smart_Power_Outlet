/**
 * Smart Power Outlet - MCP server with OAuth 2.1 (Cloudflare Worker).
 *
 * Architecture: Gemini (web / mobile / CLI) -> OAuth 2.1 -> this Worker
 * -> MQTT -> broker.hivemq.com -> Smart Power Outlet.
 *
 * The Worker runs 24/7 on Cloudflare's edge, so commands sent from a phone
 * still work when the PC is off.
 *
 * Endpoints:
 *   GET  /mcp                          MCP Streamable HTTP (needs a token)
 *   GET  /authorize                    Interactive login + consent (browser)
 *   POST /authorize                    Approve / deny a client
 *   POST /oauth/token                  Token endpoint (RFC 6749)
 *   POST /oauth/register               Dynamic Client Registration (RFC 7591)
 *   GET  /.well-known/oauth-authorization-server
 *   GET  /.well-known/oauth-protected-resource/mcp
 *   GET  /health                       Liveness probe
 *
 * Gemini Apps (gemini.google.com -> Connected Apps -> Custom apps) needs
 * OAuth 2.1 with PKCE; a static Bearer header is rejected by Google.
 */

import { OAuthProvider } from "@cloudflare/workers-oauth-provider";
import { createMcpHandler } from "agents/mcp/server";

import { handleAuthorize } from "./auth";
import {
  DEFAULTS,
  MCP_RESOURCE,
  SCOPES_SUPPORTED,
  WORKER_ORIGIN,
  type Env,
} from "./env";
import { createServer } from "./tools";

const defaultHandler = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const url = new URL(request.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({
        ok: true,
        service: "smartoutlet-mcp",
        mcpEndpoint: `${WORKER_ORIGIN}/mcp`,
        oauth: {
          issuer: WORKER_ORIGIN,
          authorizationEndpoint: `${WORKER_ORIGIN}/authorize`,
          tokenEndpoint: `${WORKER_ORIGIN}/oauth/token`,
          registrationEndpoint: `${WORKER_ORIGIN}/oauth/register`,
          scopesSupported: SCOPES_SUPPORTED,
        },
        mqtt: `${env.MQTT_HOST || DEFAULTS.MQTT_HOST}:${env.MQTT_PORT || DEFAULTS.MQTT_PORT}`,
        topic: env.MQTT_TOPIC || DEFAULTS.MQTT_TOPIC,
      });
    }

    if (url.pathname === "/authorize") {
      // The provider puts the OAuth helpers on env before calling this handler.
      const oauth = (env as Env & { OAUTH_PROVIDER?: any }).OAUTH_PROVIDER;
      if (!oauth) {
        return new Response("OAuth provider not ready", { status: 500 });
      }
      return handleAuthorize(request, env, oauth);
    }

    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;

const provider = new OAuthProvider<Env>({
  apiRoute: "/mcp",
  apiHandler: {
    async fetch(request: Request, env: Env, ctx: ExecutionContext) {
      const handler = createMcpHandler(() => createServer(env), { route: "/mcp" });
      return handler(request, env, ctx);
    },
  },
  defaultHandler,
  authorizeEndpoint: "/authorize",
  tokenEndpoint: "/oauth/token",
  clientRegistrationEndpoint: "/oauth/register",
  scopesSupported: SCOPES_SUPPORTED,
  resourceMetadata: {
    resource: MCP_RESOURCE,
    authorization_servers: [WORKER_ORIGIN],
    resource_name: "Smart Power Outlet MCP",
  },
  requiredScopes: ["mcp:read", "mcp:write"],
  clientIdMetadataDocumentEnabled: true,
  // Native Gemini mobile apps register a redirect URI with a private-use scheme.
  allowPrivateUseRedirectUris: true,
  accessTokenTTL: 60 * 60 * 12,
  refreshTokenTTL: 60 * 60 * 24 * 30,
  clientRegistrationTTL: 60 * 60 * 24 * 90,
  onError: ({ code, description, status, internal }) => {
    console.warn(`OAuth error ${status} ${code}: ${description}`, internal);
  },
});

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    // Legacy path: the old static bearer token still works for CLI clients that
    // cannot run an OAuth flow. Gemini (web/mobile) uses the OAuth path.
    if (env.MCP_TOKEN && request.headers.get("Authorization") === `Bearer ${env.MCP_TOKEN}`) {
      const handler = createMcpHandler(() => createServer(env), { route: "/mcp" });
      return handler(request, env, ctx);
    }

    return provider.fetch(request, env, ctx);
  },
} satisfies ExportedHandler<Env>;
