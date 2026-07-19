"""jarvis_cli — headless CLI for the JARVIS host.

Phase 2. Mirrors OpenClaw's ``openclaw`` command tree (which uses
``commander.js`` from ``src/cli/program/build-program.ts``). We use
Python's stdlib ``argparse`` — same shape, Python-native.

Subcommand tree::

    jarvis
      ├── tools list              # every registered tool
      ├── skills list             # every loaded SKILL.md
      ├── hooks list              # every registered hook handler
      ├── doctor [contract_id]    # run all doctor contracts (or one)
      ├── memory status           # memory_core runtime stats
      ├── memory search <query>   # substring search
      ├── memory get <key>        # read by key
      ├── cron list               # registered cron jobs
      ├── config show             # print config/jarvis.json
      └── doctor bootstrap        # re-seed the workspace files
"""
