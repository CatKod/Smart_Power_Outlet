/**
 * Minimal MQTT 3.1.1 client for Cloudflare Workers (outbound TCP via cloudflare:sockets).
 *
 * No third-party MQTT library: mqtt.js / paho-mqtt assume a Node net.Socket,
 * which does not exist in the `workerd` runtime.
 */

import { connect } from "cloudflare:sockets";

export interface MqttOptions {
  host: string;
  port: number;
  clientId: string;
  keepAliveSeconds?: number;
}

export class MqttError extends Error {
  constructor(message: string, readonly code: string) {
    super(message);
    this.name = "MqttError";
  }
}

/* ------------------------------------------------------------------ */
/* packet encoding                                                     */
/* ------------------------------------------------------------------ */

function encodeRemainingLength(length: number): Uint8Array {
  const bytes: number[] = [];
  let value = length;
  do {
    let digit = value % 128;
    value = Math.floor(value / 128);
    if (value > 0) digit |= 0x80;
    bytes.push(digit);
  } while (value > 0);
  return new Uint8Array(bytes);
}

function encodeString(text: string): Uint8Array {
  const raw = new TextEncoder().encode(text);
  const out = new Uint8Array(2 + raw.length);
  new DataView(out.buffer).setUint16(0, raw.length, false);
  out.set(raw, 2);
  return out;
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, p) => sum + p.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function connectPacket(clientId: string, keepAliveSeconds: number): Uint8Array {
  const variableHeader = concat(
    encodeString("MQTT"),
    new Uint8Array([0x04, 0x02]), // protocol name "MQTT", level 4, flags = clean session
    new Uint8Array([(keepAliveSeconds >> 8) & 0xff, keepAliveSeconds & 0xff]),
  );
  const payload = encodeString(clientId);
  const body = concat(variableHeader, payload);
  return concat(new Uint8Array([0x10]), encodeRemainingLength(body.length), body);
}

function publishPacket(
  topic: string,
  payload: string,
  qos: 0 | 1,
  packetId: number,
): Uint8Array {
  const topicBytes = encodeString(topic);
  const packetIdBytes =
    qos > 0 ? new Uint8Array([(packetId >> 8) & 0xff, packetId & 0xff]) : new Uint8Array(0);
  const payloadBytes = new TextEncoder().encode(payload);
  const body = concat(topicBytes, packetIdBytes, payloadBytes);
  const header = new Uint8Array([0x30 | (qos << 1)]);
  return concat(header, encodeRemainingLength(body.length), body);
}

function subscribePacket(topic: string, packetId: number): Uint8Array {
  const body = concat(
    new Uint8Array([(packetId >> 8) & 0xff, packetId & 0xff]),
    encodeString(topic),
    new Uint8Array([0x00]), // QoS 0
  );
  return concat(new Uint8Array([0x82]), encodeRemainingLength(body.length), body);
}

/* ------------------------------------------------------------------ */
/* packet decoding                                                     */
/* ------------------------------------------------------------------ */

export interface MqttPacket {
  type: number;
  flags: number;
  payload: Uint8Array;
}

/**
 * Buffered reader over a ReadableStream.
 *
 * `reader.read()` may return a chunk holding several packets at once, so the
 * raw bytes must be kept in a buffer between packets. Reading byte-by-byte
 * straight from the stream silently drops the tail of every chunk.
 */
class ByteReader {
  private buffer = new Uint8Array(0);
  private pending: Promise<void> | null = null;
  private finished = false;

  constructor(private readonly reader: ReadableStreamDefaultReader<Uint8Array>) {}

  private async pump(): Promise<void> {
    const { done, value } = await this.reader.read();
    if (done) {
      this.finished = true;
      return;
    }
    if (!value || value.length === 0) return;
    const merged = new Uint8Array(this.buffer.length + value.length);
    merged.set(this.buffer, 0);
    merged.set(value, this.buffer.length);
    this.buffer = merged;
  }

  /** Wait until at least `count` bytes are buffered. Returns false on EOF. */
  async ensure(count: number): Promise<boolean> {
    while (this.buffer.length < count && !this.finished) {
      if (!this.pending) {
        this.pending = this.pump().finally(() => {
          this.pending = null;
        });
      }
      await this.pending;
    }
    return this.buffer.length >= count;
  }

  take(count: number): Uint8Array {
    const out = this.buffer.subarray(0, count);
    this.buffer = this.buffer.subarray(count);
    return out;
  }
}

async function readPacket(
  reader: ByteReader,
  timeoutMs: number,
): Promise<MqttPacket | null> {
  const timeout = new Promise<null>((resolve) =>
    setTimeout(() => resolve(null), timeoutMs),
  );
  const work = (async (): Promise<MqttPacket | null> => {
    if (!(await reader.ensure(1))) return null;
    const header = reader.take(1)[0];

    let multiplier = 1;
    let remaining = 0;
    for (;;) {
      if (!(await reader.ensure(1))) return null;
      const byte = reader.take(1)[0];
      remaining += (byte & 0x7f) * multiplier;
      multiplier *= 128;
      if ((byte & 0x80) === 0) break;
    }

    if (!(await reader.ensure(remaining))) return null;
    const body = reader.take(remaining);

    return { type: header >> 4, flags: header & 0x0f, payload: body };
  })();

  return Promise.race([work, timeout]);
}

function decodeTopic(payload: Uint8Array): { topic: string; rest: Uint8Array } {
  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const length = view.getUint16(0, false);
  const topic = new TextDecoder().decode(payload.subarray(2, 2 + length));
  return { topic, rest: payload.subarray(2 + length) };
}

/* ------------------------------------------------------------------ */
/* session                                                              */
/* ------------------------------------------------------------------ */

async function openSession(options: MqttOptions) {
  const socket = connect(
    { hostname: options.host, port: options.port },
    { secureTransport: "off", allowHalfOpen: false },
  );

  // Surface the real connection error instead of a downstream timeout.
  try {
    await socket.opened;
  } catch (error) {
    try {
      socket.close();
    } catch {
      /* ignore */
    }
    throw new MqttError(
      `Không kết nối được TCP tới ${options.host}:${options.port}: ` +
        (error instanceof Error ? error.message : String(error)),
      "TCP_CONNECT_FAILED",
    );
  }

  const writer = socket.writable.getWriter();
  const rawReader = socket.readable.getReader();
  const reader = new ByteReader(rawReader);

  await writer.write(
    connectPacket(options.clientId, options.keepAliveSeconds ?? 30),
  );

  const connack = await readPacket(reader, 10_000);
  if (!connack) {
    socket.close();
    throw new MqttError(
      `Không nhận được CONNACK từ ${options.host}:${options.port} (timeout)`,
      "CONNACK_TIMEOUT",
    );
  }
  if (connack.type !== 2) {
    socket.close();
    throw new MqttError(
      `Broker trả về packet type ${connack.type} thay vì CONNACK`,
      "BAD_CONNACK",
    );
  }
  const returnCode = connack.payload.length > 1 ? connack.payload[1] : -1;
  if (returnCode !== 0) {
    socket.close();
    const reasons = [
      "Accepted",
      "Unacceptable protocol version",
      "Identifier rejected",
      "Server unavailable",
      "Bad user name or password",
      "Not authorized",
    ];
    throw new MqttError(
      `Broker từ chối kết nối: rc=${returnCode} (${reasons[returnCode] ?? "unknown"})`,
      "CONNACK_REJECTED",
    );
  }

  return { socket, writer, reader };
}

/* ------------------------------------------------------------------ */
/* public API                                                           */
/* ------------------------------------------------------------------ */

export interface PublishResult {
  topic: string;
  payload: string;
  qos: 0 | 1;
  acknowledged: boolean;
  packetId: number;
}

/** Publish one message and wait for the broker acknowledgement (QoS 1). */
export async function publish(
  options: MqttOptions,
  topic: string,
  payload: string,
  qos: 0 | 1 = 1,
): Promise<PublishResult> {
  const { socket, writer, reader } = await openSession(options);
  const packetId = Math.floor(Math.random() * 0xffff) + 1;
  try {
    await writer.write(publishPacket(topic, payload, qos, packetId));
    if (qos === 0) {
      return { topic, payload, qos, acknowledged: true, packetId };
    }
    const ack = await readPacket(reader, 10_000);
    if (!ack) {
      throw new MqttError(
        `Không nhận được PUBACK cho topic ${topic} (timeout)`,
        "PUBACK_TIMEOUT",
      );
    }
    if (ack.type !== 4) {
      throw new MqttError(
        `Broker trả về packet type ${ack.type} thay vì PUBACK`,
        "BAD_PUBACK",
      );
    }
    return { topic, payload, qos, acknowledged: true, packetId };
  } finally {
    try {
      socket.close();
    } catch {
      /* already closed */
    }
  }
}

export interface SubscribeResult {
  topic: string;
  messages: { topic: string; payload: string }[];
}

/** Subscribe to one topic and collect messages for a bounded window. */
export async function subscribeAndCollect(
  options: MqttOptions,
  topic: string,
  collectMs: number,
  maxMessages: number,
): Promise<SubscribeResult> {
  const { socket, writer, reader } = await openSession(options);
  const packetId = Math.floor(Math.random() * 0xffff) + 1;
  const messages: { topic: string; payload: string }[] = [];
  try {
    await writer.write(subscribePacket(topic, packetId));
    const suback = await readPacket(reader, 10_000);
    if (!suback || suback.type !== 9) {
      throw new MqttError(
        `Không nhận được SUBACK cho topic ${topic}`,
        "SUBACK_TIMEOUT",
      );
    }
    const deadline = Date.now() + collectMs;
    while (messages.length < maxMessages && Date.now() < deadline) {
      const packet = await readPacket(reader, Math.max(250, deadline - Date.now()));
      if (!packet) break;
      if (packet.type !== 3) continue;
      const { topic: messageTopic, rest } = decodeTopic(packet.payload);
      messages.push({
        topic: messageTopic,
        payload: new TextDecoder().decode(rest),
      });
    }
    return { topic, messages };
  } finally {
    try {
      socket.close();
    } catch {
      /* already closed */
    }
  }
}
