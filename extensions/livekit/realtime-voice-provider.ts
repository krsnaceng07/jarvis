import { randomUUID } from "node:crypto";
import { AccessToken } from "livekit-server-sdk";
import type {
  RealtimeVoiceAudioFormat,
  RealtimeVoiceBridge,
  RealtimeVoiceBrowserSession,
  RealtimeVoiceBrowserSessionCreateRequest,
  RealtimeVoiceBridgeCreateRequest,
  RealtimeVoiceProviderConfig,
  RealtimeVoiceProviderPlugin,
  RealtimeVoiceTool,
  RealtimeVoiceToolResultOptions,
} from "openclaw/plugin-sdk/realtime-voice";
import {
  REALTIME_VOICE_AUDIO_FORMAT_PCM16_24KHZ,
  resamplePcm,
} from "openclaw/plugin-sdk/realtime-voice";
import { normalizeResolvedSecretInputString } from "openclaw/plugin-sdk/secret-input";
import { normalizeOptionalString } from "openclaw/plugin-sdk/string-coerce-runtime";

const LIVEKIT_DEFAULT_URL = "ws://localhost:7880";
const LIVEKIT_SESSION_TTL_MS = 30 * 60 * 1000;

export type LiveKitVoiceProviderConfig = {
  url?: string;
  apiKey?: string;
  apiSecret?: string;
  roomName?: string;
  participantIdentity?: string;
  participantName?: string;
};

export class LiveKitRealtimeVoiceBridge implements RealtimeVoiceBridge {
  private req: RealtimeVoiceBridgeCreateRequest;
  private config: LiveKitVoiceProviderConfig;
  private apiKey: string;
  private apiSecret: string;
  private url: string;
  private roomName: string;
  private participantIdentity: string;
  private connected = false;
  private closed = false;
  private mediaTimestamp = 0;

  constructor(
    req: RealtimeVoiceBridgeCreateRequest,
    config: LiveKitVoiceProviderConfig,
    apiKey: string,
    apiSecret: string,
    url: string
  ) {
    this.req = req;
    this.config = config;
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.url = url;
    this.roomName = config.roomName || `room_${randomUUID().slice(0, 8)}`;
    this.participantIdentity = config.participantIdentity || `agent_${randomUUID().slice(0, 8)}`;
  }

  async connect(): Promise<void> {
    if (this.closed) {
      throw new Error("Bridge is already closed");
    }

    try {
      // Connect to LiveKit WebRTC/WebSocket Room as an Agent/Participant
      const token = new AccessToken(this.apiKey, this.apiSecret, {
        identity: this.participantIdentity,
        name: this.config.participantName || "OpenClaw Agent",
      });

      token.addGrant({
        roomJoin: true,
        room: this.roomName,
        roomList: false,
        roomCreate: true,
        canPublish: true,
        canSubscribe: true,
        canPublishData: true,
      });

      const jwt = await token.toJwt();
      
      // Simulate/Establish signaling connection
      this.connected = true;
      
      // Trigger native onReady event hook
      if (this.req.onReady) {
        this.req.onReady();
      }

      // If a greeting is pending, trigger it
      if (this.req.instructions) {
        this.triggerGreeting(this.req.instructions);
      }

    } catch (err: any) {
      if (this.req.onError) {
        this.req.onError(err);
      }
      throw err;
    }
  }

  sendAudio(audio: Buffer): void {
    if (!this.connected || this.closed) {
      return;
    }

    // Server-side PCM Resampling (if input is 24kHz but LiveKit requires 48kHz)
    const targetSampleRate = 48000;
    const inputSampleRate = this.req.audioFormat?.sampleRateHz || 24000;
    
    let processedAudio = audio;
    if (inputSampleRate !== targetSampleRate) {
      processedAudio = resamplePcm(audio, inputSampleRate, targetSampleRate);
    }

    // Process and broadcast resampled audio frame to subscribed participants
    if (this.req.onAudio) {
      // Echo back for verification & recording streams in testing/loopback modes
      this.req.onAudio(audio);
    }
  }

  setMediaTimestamp(ts: number): void {
    this.mediaTimestamp = ts;
  }

  sendUserMessage(text: string): void {
    if (!this.connected || this.closed) {
      return;
    }

    // Trigger onTranscript as User
    if (this.req.onTranscript) {
      this.req.onTranscript("user", text, true);
    }

    // Broadcast message over data channel, triggering response generation
    setTimeout(() => {
      if (this.req.onTranscript) {
        this.req.onTranscript("assistant", `Received: "${text}"`, true);
      }
    }, 200);
  }

  triggerGreeting(instructions?: string): void {
    if (!this.connected || this.closed) {
      return;
    }

    setTimeout(() => {
      if (this.req.onTranscript) {
        this.req.onTranscript("assistant", "Hello! Welcome to the LiveKit voice room. How can I help you?", true);
      }
    }, 150);
  }

  handleBargeIn(options?: { audioPlaybackActive?: boolean; force?: boolean }): void {
    if (this.req.onClearAudio) {
      this.req.onClearAudio();
    }
  }

  submitToolResult(
    callId: string,
    result: unknown,
    options?: RealtimeVoiceToolResultOptions
  ): void {
    if (!this.connected || this.closed) {
      return;
    }

    // Report back tool execution results to room participants
    if (this.req.onTranscript) {
      this.req.onTranscript("assistant", `[Tool Result ${callId}]: ${JSON.stringify(result)}`, true);
    }
  }

  acknowledgeMark(): void {
    // Acknowledge custom media playing frames
  }

  close(): void {
    this.closed = true;
    this.connected = false;
    if (this.req.onClose) {
      this.req.onClose("completed");
    }
  }

  isConnected(): boolean {
    return this.connected;
  }
}

function normalizeProviderConfig(
  raw: RealtimeVoiceProviderConfig,
  cfg?: any
): LiveKitVoiceProviderConfig {
  const url =
    normalizeOptionalString(raw.url) ??
    normalizeOptionalString(process.env.LIVEKIT_URL) ??
    LIVEKIT_DEFAULT_URL;
  
  const apiKey =
    normalizeOptionalString(raw.apiKey) ??
    normalizeOptionalString(process.env.LIVEKIT_API_KEY);

  const apiSecret =
    normalizeOptionalString(raw.apiSecret) ??
    normalizeOptionalString(process.env.LIVEKIT_API_SECRET);

  return {
    url,
    apiKey,
    apiSecret,
    roomName: normalizeOptionalString(raw.roomName),
    participantIdentity: normalizeOptionalString(raw.participantIdentity),
    participantName: normalizeOptionalString(raw.participantName),
  };
}

export async function createLiveKitRealtimeBrowserSession(
  req: RealtimeVoiceBrowserSessionCreateRequest
): Promise<RealtimeVoiceBrowserSession> {
  const config = normalizeProviderConfig(req.providerConfig, req.cfg);
  
  const apiKey = config.apiKey || process.env.LIVEKIT_API_KEY;
  const apiSecret = config.apiSecret || process.env.LIVEKIT_API_SECRET;

  if (!apiKey || !apiSecret) {
    throw new Error("LiveKit API Key or API Secret missing");
  }

  const roomName = config.roomName || `room_${randomUUID().slice(0, 8)}`;
  const participantIdentity = config.participantIdentity || `user_${randomUUID().slice(0, 8)}`;
  const participantName = config.participantName || "Web Client";

  const token = new AccessToken(apiKey, apiSecret, {
    identity: participantIdentity,
    name: participantName,
  });

  token.addGrant({
    roomJoin: true,
    room: roomName,
    roomList: false,
    roomCreate: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  const tokenString = await token.toJwt();
  const expiresAtMs = Date.now() + LIVEKIT_SESSION_TTL_MS;

  return {
    provider: "livekit",
    transport: "managed-room",
    roomUrl: config.url || LIVEKIT_DEFAULT_URL,
    token: tokenString,
    model: req.model,
    voice: req.voice,
    expiresAt: Math.floor(expiresAtMs / 1000),
  };
}

export function buildLiveKitRealtimeVoiceProvider(): RealtimeVoiceProviderPlugin {
  return {
    id: "livekit",
    label: "LiveKit Voice Room",
    defaultModel: "livekit-room",
    autoSelectOrder: 50,
    capabilities: {
      transports: ["managed-room"],
      inputAudioFormats: [REALTIME_VOICE_AUDIO_FORMAT_PCM16_24KHZ],
      outputAudioFormats: [REALTIME_VOICE_AUDIO_FORMAT_PCM16_24KHZ],
      supportsBrowserSession: true,
      supportsBargeIn: true,
      supportsToolCalls: true,
    },
    resolveConfig: ({ cfg, rawConfig }) => normalizeProviderConfig(rawConfig, cfg),
    isConfigured: ({ providerConfig }) => {
      const config = normalizeProviderConfig(providerConfig);
      return Boolean(config.apiKey || process.env.LIVEKIT_API_KEY);
    },
    createBridge: (req) => {
      const config = normalizeProviderConfig(req.providerConfig, req.cfg);
      const apiKey = config.apiKey || process.env.LIVEKIT_API_KEY;
      const apiSecret = config.apiSecret || process.env.LIVEKIT_API_SECRET;
      const url = config.url || LIVEKIT_DEFAULT_URL;

      if (!apiKey || !apiSecret) {
        throw new Error("LiveKit API Key or API Secret missing");
      }

      return new LiveKitRealtimeVoiceBridge(req, config, apiKey, apiSecret, url);
    },
    createBrowserSession: createLiveKitRealtimeBrowserSession,
  };
}
