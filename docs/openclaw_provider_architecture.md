# OpenClaw Provider Architecture

This document details model and inference provider management in OpenClaw (`v2026.9.2`).

---

## 1. Provider Abstraction Contract

OpenClaw supports heterogeneous AI backends through clean provider interfaces:
- **`ProviderPlugin`**: Text generation, chat completion, and tool invocation.
- **`EmbeddingProviderAdapter`**: Dense vector generation for memory indexing.
- **`SpeechProviderPlugin`**: Text-to-speech (TTS) streaming synthesis.
- **`RealtimeVoiceProviderPlugin`**: Full-duplex WebRTC / LiveKit conversational audio.
- **`MediaUnderstandingProviderPlugin`**: Image OCR, visual Q&A, and audio transcription.

---

## 2. Registration & Discovery

Providers register through `PluginApi`:

```typescript
api.registerProvider(buildOpenAIProvider());
api.registerEmbeddingProvider(openAiMemoryEmbeddingProviderAdapter);
api.registerSpeechProvider(buildOpenAISpeechProvider());
api.registerRealtimeVoiceProvider(buildOpenAIRealtimeVoiceProvider);
```

The host aggregates these into the `PluginRegistry`:
- `registry.providers`
- `registry.embeddingProviders`
- `registry.speechProviders`
- `registry.realtimeVoiceProviders`

---

## 3. Dynamic Selection & Failover Cascades

1. **Capability Flags**: Models declare supported features (`supportsStreaming`, `supportsTools`, `supportsVision`, `supportsJsonSchema`).
2. **Priority Selection**: Primary model is selected by default; if unavailable or rate-limited, the router cascades to configured fallback providers (`provider-runtime`).
3. **Circuit Breakers & Retries**: Transient HTTP errors (429, 503) trigger jittered exponential backoff before falling back.
