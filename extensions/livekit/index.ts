import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { RealtimeVoiceProviderPlugin } from "openclaw/plugin-sdk/realtime-voice";

let livekitRealtimeVoiceProviderPromise: Promise<RealtimeVoiceProviderPlugin> | null = null;

async function loadLiveKitRealtimeVoiceProvider(): Promise<RealtimeVoiceProviderPlugin> {
  if (!livekitRealtimeVoiceProviderPromise) {
    livekitRealtimeVoiceProviderPromise = import("./realtime-voice-provider.js").then((mod) =>
      mod.buildLiveKitRealtimeVoiceProvider(),
    );
  }
  return await livekitRealtimeVoiceProviderPromise;
}

function createLazyLiveKitRealtimeVoiceProvider(): RealtimeVoiceProviderPlugin {
  return {
    id: "livekit",
    label: "LiveKit Voice Room",
    defaultModel: "livekit-room",
    autoSelectOrder: 50,
    resolveConfig: (ctx) => {
      const raw = ctx.rawConfig || {};
      return {
        url: typeof raw.url === "string" ? raw.url : process.env.LIVEKIT_URL,
        apiKey: typeof raw.apiKey === "string" ? raw.apiKey : process.env.LIVEKIT_API_KEY,
        apiSecret: typeof raw.apiSecret === "string" ? raw.apiSecret : process.env.LIVEKIT_API_SECRET,
      };
    },
    isConfigured: ({ providerConfig }) => {
      return Boolean(
        providerConfig.apiKey ||
        process.env.LIVEKIT_API_KEY
      );
    },
    createBridge: (req) => {
      let bridge: any;
      let bridgePromise: Promise<any> | undefined;
      const loadBridge = async () => {
        if (!bridgePromise) {
          bridgePromise = loadLiveKitRealtimeVoiceProvider().then((provider) =>
            provider.createBridge(req)
          );
        }
        bridge = await bridgePromise;
        return bridge;
      };
      return {
        connect: async () => {
          const loaded = await loadBridge();
          await loaded.connect();
        },
        sendAudio: (audio) => {
          bridge?.sendAudio(audio);
        },
        setMediaTimestamp: (ts) => {
          bridge?.setMediaTimestamp(ts);
        },
        sendUserMessage: (text) => {
          bridge?.sendUserMessage?.(text);
        },
        triggerGreeting: (instructions) => {
          bridge?.triggerGreeting?.(instructions);
        },
        submitToolResult: (callId, result, options) => {
          bridge?.submitToolResult(callId, result, options);
        },
        acknowledgeMark: () => {
          bridge?.acknowledgeMark();
        },
        close: () => {
          bridge?.close();
        },
        isConnected: () => {
          return bridge?.isConnected() ?? false;
        }
      };
    },
    createBrowserSession: async (req) => {
      const provider = await loadLiveKitRealtimeVoiceProvider();
      if (!provider.createBrowserSession) {
        throw new Error("LiveKit provider missing createBrowserSession");
      }
      return await provider.createBrowserSession(req);
    }
  };
}

export default definePluginEntry({
  id: "livekit",
  name: "LiveKit Plugin",
  description: "Native LiveKit WebRTC Voice Room Provider plugin",
  register(api) {
    api.registerRealtimeVoiceProvider(createLazyLiveKitRealtimeVoiceProvider());
  }
});
