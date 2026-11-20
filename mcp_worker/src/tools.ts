/**
 * MCP tool definitions for the Smart Power Outlet.
 *
 * Each tool publishes/subscribes on the MQTT broker through `mqtt.ts`.
 */

import { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";

import { publish, subscribeAndCollect, type MqttOptions } from "./mqtt";
import { DEFAULTS, type Env } from "./env";

function mqttOptions(env: Env): MqttOptions {
  return {
    host: env.MQTT_HOST || DEFAULTS.MQTT_HOST,
    port: Number(env.MQTT_PORT || DEFAULTS.MQTT_PORT),
    clientId: `smartoutlet-${crypto.randomUUID().slice(0, 8)}`,
    keepAliveSeconds: 30,
  };
}

function buildCommandPayload(command: string, note?: string) {
  return JSON.stringify({
    cmd: command.toUpperCase(),
    note: note ?? "",
    source: "mcp-worker",
    ts: new Date().toISOString(),
  });
}

export function createServer(env: Env) {
  const server = new McpServer({
    name: "smartoutlet",
    version: "0.2.0",
  });

  server.registerTool(
    "send_command",
    {
      title: "Gửi lệnh tới ổ cắm",
      description:
        "Gửi lệnh điều khiển tới thiết bị Smart Power Outlet qua MQTT. " +
        "command là 'on' để bật hoặc 'off' để tắt.",
      inputSchema: z.object({
        command: z
          .enum(["on", "off", "ON", "OFF"])
          .describe("Lệnh cần gửi: 'on' bật, 'off' tắt"),
        note: z
          .string()
          .optional()
          .describe("Ghi chú tùy chọn, ví dụ 'bật quạt tủ rack'"),
      }),
      outputSchema: z.object({
        ok: z.boolean(),
        topic: z.string(),
        payload: z.string(),
        acknowledged: z.boolean(),
      }),
      annotations: { destructiveHint: true, openWorldHint: true },
    },
    async ({ command, note }) => {
      const topic = env.MQTT_TOPIC || DEFAULTS.MQTT_TOPIC;
      const payload = buildCommandPayload(command, note);
      try {
        const result = await publish(mqttOptions(env), topic, payload, 1);
        const output = {
          ok: true,
          topic: result.topic,
          payload: result.payload,
          acknowledged: result.acknowledged,
        };
        return {
          content: [
            {
              type: "text" as const,
              text:
                `Đã gửi lệnh ${command.toUpperCase()} tới topic "${topic}". ` +
                `Broker đã xác nhận (QoS 1). Payload: ${payload}`,
            },
          ],
          structuredContent: output,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          content: [
            { type: "text" as const, text: `Gửi lệnh thất bại: ${message}` },
          ],
          isError: true,
        };
      }
    },
  );

  server.registerTool(
    "read_last_message",
    {
      title: "Đọc tin nhắn gần nhất",
      description:
        "Subscribe ngắn hạn vào topic để đọc trạng thái/telemetry gần nhất " +
        "mà thiết bị hoặc agent đã publish.",
      inputSchema: z.object({
        waitSeconds: z
          .number()
          .int()
          .min(1)
          .max(30)
          .optional()
          .describe("Số giây chờ nhận tin nhắn (mặc định 5)"),
        maxMessages: z
          .number()
          .int()
          .min(1)
          .max(20)
          .optional()
          .describe("Số tin nhắn tối đa (mặc định 5)"),
      }),
      outputSchema: z.object({
        topic: z.string(),
        count: z.number(),
        messages: z.array(z.object({ topic: z.string(), payload: z.string() })),
      }),
      annotations: { readOnlyHint: true, openWorldHint: true },
    },
    async ({ waitSeconds, maxMessages }) => {
      const topic = env.MQTT_TOPIC || DEFAULTS.MQTT_TOPIC;
      try {
        const result = await subscribeAndCollect(
          mqttOptions(env),
          topic,
          (waitSeconds ?? 5) * 1000,
          maxMessages ?? 5,
        );
        const text = result.messages.length
          ? result.messages.map((m) => `- ${m.topic}: ${m.payload}`).join("\n")
          : "Không nhận được tin nhắn nào trong thời gian chờ.";
        return {
          content: [{ type: "text" as const, text }],
          structuredContent: {
            topic,
            count: result.messages.length,
            messages: result.messages,
          },
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          content: [
            { type: "text" as const, text: `Đọc tin nhắn thất bại: ${message}` },
          ],
          isError: true,
        };
      }
    },
  );

  server.registerTool(
    "server_status",
    {
      title: "Trạng thái máy chủ",
      description: "Trả về cấu hình broker/topic hiện tại của MCP server.",
      inputSchema: z.object({}),
      outputSchema: z.object({
        mqttHost: z.string(),
        mqttPort: z.number(),
        topic: z.string(),
        serverTime: z.string(),
      }),
      annotations: { readOnlyHint: true },
    },
    async () => {
      const output = {
        mqttHost: env.MQTT_HOST || DEFAULTS.MQTT_HOST,
        mqttPort: Number(env.MQTT_PORT || DEFAULTS.MQTT_PORT),
        topic: env.MQTT_TOPIC || DEFAULTS.MQTT_TOPIC,
        serverTime: new Date().toISOString(),
      };
      return {
        content: [{ type: "text" as const, text: JSON.stringify(output, null, 2) }],
        structuredContent: output,
      };
    },
  );

  return server;
}
