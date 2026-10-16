# OpenClaw Complete Repository & Architectural Structure

This document provides a comprehensive structural mapping of the reference OpenClaw codebase (2026.9.2), including top-level directories, internal packages, extensions, and runtime modules.

---

## 1. Top-Level Directory Layout

`	ext
openclaw/
├── .agents/                    # Agent skills, instructions, and maintenance workflows
├── .github/                    # CI/CD workflows, issue/PR labelers, actions
├── apps/                       # Multi-platform client applications
│   ├── android/                # Android companion client
│   ├── ios/                    # iOS client application
│   ├── linux/                  # Linux system tray / indicator service
│   ├── macos/                  # Native macOS status bar and menu bar app
│   ├── mobile/                 # Shared React Native mobile codebase
│   └── swabble/                # Ambient voice / microphone hotword listener
├── config/                     # Core schema definitions and path resolvers
├── custodian-skills/           # Repository health, diagnose, and triage automation
├── deploy/                     # Dockerfiles, docker-compose, and deployment templates
├── docs/                       # Architectural documentation, guides, and channel manuals
├── examples/                   # Sample extensions, MCP integrations, and plugins
├── extensions/                 # 153 bundled plugins (channels, providers, tools, memory)
├── git-hooks/                  # Pre-commit, commit-msg, and branch validation hooks
├── packages/                   # 23 internal workspace libraries
├── patches/                    # pnpm package patches for upstream dependencies
├── qa/                         # Automated QA scenarios, lab tests, and stress campaigns
├── scripts/                    # Development, build, benchmark, and release scripts
├── security/                   # Opengrep rules, sandbox profiles, and security scanners
├── skills/                     # Declarative agent skills with markdown frontmatter
├── src/                        # Core Gateway server runtime, agents, daemon, CLI
├── test/                       # Unit, integration, and E2E test suites
└── ui/                         # Control UI web frontend (Lit / WebAwesome dashboard)
`

---

## 2. Workspace Packages (packages/)

The 23 packages in packages/ are managed via pnpm-workspace.yaml:

`	ext
packages/
├── acp-core/                   # Agent Communication Protocol interfaces
├── agent-core/                 # Turn lifecycle and prompt preparation primitives
├── ai/                         # Unified AI client interfaces
├── gateway-client/             # WebSocket JSON-RPC gateway client
├── gateway-protocol/           # Protocol method descriptors and event schemas
├── llm-core/                   # LLM turn execution and token chunking
├── markdown-core/              # Streaming markdown parser and rich block splitter
├── media-core/                 # Image/video/audio transcoding and MIME detection
├── media-generation-core/      # Interfaces for image, video, and audio generation
├── media-understanding-common/ # STT, TTS, and multimodal vision abstractions
├── memory-host-sdk/            # Host contract for memory backends and embedding providers
├── mermaid-renderer/           # Mermaid diagram rendering engine
├── model-catalog-core/         # Model definitions, context windows, and cost metadata
├── net-policy/                 # SSRF guards and network egress policies
├── normalization-core/         # Portable string and address normalizers
├── plugin-package-contract/    # Plugin manifest schemas and package validation
├── plugin-sdk/                 # Narrow subpath exports for extension authors
├── retry/                      # Exponential backoff and retry mechanisms
├── sdk/                        # Top-level client SDK facade
├── session-url-contract/       # Deep linking and WebApp URL generation
├── terminal-core/              # Sandboxed terminal / PTY execution contract
├── tool-call-repair/           # Robust JSON repair for malformed LLM tool calls
└── workboard-contract/         # Visual taskboard, card, and workflow state contracts
`

---

## 3. Core Runtime Subsystems (src/)

`	ext
src/
├── acp/                        # Agent Communication Protocol server & adapters
├── agents/                     # Embedded agent runner, prompt compiler, tool engine
│   ├── embedded-agent-runner/  # Main execution loop for agent turns
│   ├── harness/                # Test and execution harnesses
│   ├── main-session-recovery/  # Restart and crash recovery for sessions
│   ├── models/                 # Model adapters and execution wrappers
│   └── tools/                  # Built-in agent tools (bash, fs, browser, etc.)
├── audit/                      # Audit trails and compliance logging
├── auto-reply/                 # Inbound message deduplication, debouncing, and reply routing
├── boards/                     # Workboard and Kanban backend services
├── canvas/                     # Interactive visual canvas and widget rendering
├── channels/                   # Multi-channel turn runner, session routing, allowlists
│   ├── inbound-event/          # Inbound event context and classification
│   ├── plugins/                # Channel plugin base contracts
│   └── turn/                   # 5-stage turn execution pipeline
├── chat/                       # Chat session state and message stores
├── claws/                      # Autonomous background agent workers
├── cli/                        # Command line interface commands and subcommands
├── commands/                   # Portable slash command handlers
├── compat/                     # Backwards compatibility migrations
├── config/                     # Configuration I/O, schema migrations, environment parsing
├── context-engine/             # Sliding context window management and token budget pruning
├── cron/                       # Scheduled background tasks and cron store
├── daemon/                     # OS service manager (systemd, launchd, Windows Service)
├── docs/                       # Embedded documentation providers
├── fleet/                      # Multi-node gateway fleet management
├── flows/                      # Workflow and DAG execution engine
├── gateway/                    # HTTP/WebSocket gateway server, auth, and dispatch
├── hooks/                      # Internal hook bus, event emission, and subscribers
├── image-generation/           # Image generation supervisor and cache
├── infra/                      # Security policies, execution approvals, safe binaries
├── interactive/                # Interactive prompt and approval sessions
├── link-understanding/         # URL preview and link metadata scraper
├── llm/                        # LLM provider dispatch and streaming aggregator
├── logging/                    # Structured JSON logging and subsystem loggers
├── mcp/                        # Model Context Protocol host and client implementation
├── media/                      # Media storage, caching, and streaming
├── media-generation/           # Video and music synthesis coordination
├── media-understanding/        # Speech recognition, audio synthesis, and OCR
├── meeting-bot/                # Google Meet / Zoom / Teams virtual meeting participant
├── memory/                     # Memory retrieval coordinators and indexers
├── memory-host-sdk/            # Host bindings for memory extensions
├── model-catalog/              # Dynamic model discovery and capability indexing
├── model-picker/               # Automatic model selection based on task complexity
├── music-generation/           # Music generation engine
├── node-host/                  # Distributed worker node management
├── pairing/                    # Channel pairing and user authorization
├── plugin-sdk/                 # Implementation of plugin SDK runtime helpers
├── plugin-state/               # SQLite and keyed store state for plugins
├── plugins/                    # Plugin discovery, manifest validation, lifecycle loader
├── process/                    # Subprocess supervision and command queue
├── projects/                   # Project workspace isolation and multi-tenancy
├── provider-runtime/           # LLM provider routing and failover
├── proxy-capture/              # HTTP proxy and traffic inspection
├── realtime-transcription/     # Realtime streaming audio transcription
├── routing/                    # Session and conversation routing
├── secrets/                    # Secret management, 1Password/Vault adapters, masking
├── security/                   # Sandbox isolation, security audit, permission checks
├── session-cards/              # Rich session cards and message rendering
├── sessions/                   # Session persistence, maintenance, and compaction
├── shared/                     # Shared cross-cutting utilities
├── skills/                     # Declarative skill parser and interpolation engine
├── snapshot/                   # Runtime state snapshots and checkpoints
├── state/                      # Database migrations, SQLite schemas, integrity checks
├── status/                     # Health check status, issues, and diagnostics
├── system-agent/               # Internal maintenance and self-healing agent
├── talk/                       # Realtime voice conversations and duplex audio
├── tasks/                      # Background task ledger and detached tasks
├── trajectory/                 # Agent step execution trajectories and replay logs
├── transcripts/                # Conversation transcript storage and sanitization
├── tts/                        # Text-to-speech coordination and playback
├── tui/                        # Terminal user interface
├── types/                      # Global TypeScript type definitions
├── utils/                      # Low-level helper functions
├── video-generation/           # Video synthesis pipeline
├── web/                        # Web server utilities and HTTP route dispatch
├── web-fetch/                  # Safe HTTP fetch with SSRF guards
├── web-search/                 # Multi-provider web search routing
├── wizard/                     # Onboarding and configuration wizards
└── worker/                     # Detached background worker processes
`
