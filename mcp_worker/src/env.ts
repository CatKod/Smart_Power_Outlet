/**
 * Shared configuration for the Smart Power Outlet MCP Worker.
 */

export interface Env {
  /** Legacy static bearer token. Still accepted for CLI clients; empty = disabled. */
  MCP_TOKEN: string;
  /** Password required to sign in on the /authorize page. */
  LOGIN_PASSWORD: string;
  /** Secret used to sign session cookies and remembered consents (32+ chars). */
  AUTH_SECRET: string;
  /** KV namespace backing the OAuth provider (tokens, clients, grants). */
  OAUTH_KV: KVNamespace;
  /** MQTT broker hostname. */
  MQTT_HOST: string;
  /** MQTT broker port (default 1883). */
  MQTT_PORT: string;
  /** Topic used for commands and telemetry. */
  MQTT_TOPIC: string;
}

export const DEFAULTS = {
  MQTT_HOST: "broker.hivemq.com",
  MQTT_PORT: "1883",
  MQTT_TOPIC: "hoangkimvinh",
};

/** Canonical public URL of this Worker. */
export const WORKER_ORIGIN = "https://smartoutlet-mcp.kimvinhh6.workers.dev";

/** Canonical RFC 9728 resource identifier of the MCP endpoint. */
export const MCP_RESOURCE = `${WORKER_ORIGIN}/mcp`;

/** Scopes this authorization server can grant. */
export const SCOPES_SUPPORTED = ["mcp:read", "mcp:write", "offline_access"];
