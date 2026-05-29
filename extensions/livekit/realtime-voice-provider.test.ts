import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { buildLiveKitRealtimeVoiceProvider } from "./realtime-voice-provider.js";
import { AccessToken } from "livekit-server-sdk";

describe("LiveKit Realtime Voice Provider", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it("should build provider with correct capabilities", () => {
    const provider = buildLiveKitRealtimeVoiceProvider();
    expect(provider.id).toBe("livekit");
    expect(provider.label).toBe("LiveKit Voice Room");
    expect(provider.defaultModel).toBe("livekit-room");
    expect(provider.capabilities).toBeDefined();
    expect(provider.capabilities?.transports).toContain("managed-room");
  });

  describe("isConfigured", () => {
    it("should return false if credentials are missing", () => {
      delete process.env.LIVEKIT_API_KEY;
      delete process.env.LIVEKIT_API_SECRET;
      const provider = buildLiveKitRealtimeVoiceProvider();
      expect(provider.isConfigured({ providerConfig: {} })).toBe(false);
    });

    it("should return true if API key is present in config", () => {
      const provider = buildLiveKitRealtimeVoiceProvider();
      expect(provider.isConfigured({ providerConfig: { apiKey: "test-key" } })).toBe(true);
    });

    it("should return true if API key is present in environment", () => {
      process.env.LIVEKIT_API_KEY = "env-key";
      const provider = buildLiveKitRealtimeVoiceProvider();
      expect(provider.isConfigured({ providerConfig: {} })).toBe(true);
    });
  });

  describe("resolveConfig", () => {
    it("should resolve configuration with defaults", () => {
      process.env.LIVEKIT_URL = "wss://project.livekit.cloud";
      process.env.LIVEKIT_API_KEY = "env-key";
      process.env.LIVEKIT_API_SECRET = "env-secret";

      const provider = buildLiveKitRealtimeVoiceProvider();
      const config = provider.resolveConfig!({ cfg: {}, rawConfig: {} });

      expect(config.url).toBe("wss://project.livekit.cloud");
      expect(config.apiKey).toBe("env-key");
      expect(config.apiSecret).toBe("env-secret");
    });
  });

  describe("createBrowserSession", () => {
    it("should throw error if credentials are missing", async () => {
      delete process.env.LIVEKIT_API_KEY;
      delete process.env.LIVEKIT_API_SECRET;
      const provider = buildLiveKitRealtimeVoiceProvider();
      await expect(
        provider.createBrowserSession!({ providerConfig: {} })
      ).rejects.toThrow("LiveKit API Key or API Secret missing");
    });

    it("should generate a valid JWT token browser session", async () => {
      process.env.LIVEKIT_API_KEY = "dev-key";
      process.env.LIVEKIT_API_SECRET = "dev-secret";

      const provider = buildLiveKitRealtimeVoiceProvider();
      const session = await provider.createBrowserSession!({
        providerConfig: { url: "wss://project.livekit.cloud" },
      });

      expect(session.provider).toBe("livekit");
      expect(session.transport).toBe("managed-room");
      expect(session.roomUrl).toBe("wss://project.livekit.cloud");
      expect(session.token).toBeDefined();
      expect(typeof session.token).toBe("string");
    });
  });

  describe("createBridge", () => {
    it("should throw error if credentials are missing", () => {
      delete process.env.LIVEKIT_API_KEY;
      delete process.env.LIVEKIT_API_SECRET;
      const provider = buildLiveKitRealtimeVoiceProvider();
      expect(() =>
        provider.createBridge({
          providerConfig: {},
          onAudio: vi.fn(),
          onClearAudio: vi.fn(),
        })
      ).toThrow("LiveKit API Key or API Secret missing");
    });

    it("should support bridge flow", async () => {
      process.env.LIVEKIT_API_KEY = "dev-key";
      process.env.LIVEKIT_API_SECRET = "dev-secret";

      const provider = buildLiveKitRealtimeVoiceProvider();
      const onReady = vi.fn();
      const onTranscript = vi.fn();

      const bridge = provider.createBridge({
        providerConfig: {},
        onAudio: vi.fn(),
        onClearAudio: vi.fn(),
        onReady,
        onTranscript,
      });

      expect(bridge.isConnected()).toBe(false);
      await bridge.connect();
      expect(bridge.isConnected()).toBe(true);

      bridge.sendUserMessage!("hello");
      expect(onTranscript).toHaveBeenCalledWith("user", "hello", true);

      bridge.close();
      expect(bridge.isConnected()).toBe(false);
    });
  });
});
