"""Interactive bootstrap ritual — three-beat identity ceremony (OpenClaw parity).

The ritual:
1. Ask agent name (capped to ~32 chars, stored as agent.name)
2. Ask agent soul/vibe (agent's voice/tone preferences)
3. Ask plugin preference (minimal vs. convenient plugin set)

This matches OpenClaw's bootstrap/index.ts flow. After each beat, the ritual
persists the choice to IDENTITY.md, SOUL.md, config.json (agent section).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis_config_core import JarvisConfig

_RITUAL_HEADER = """
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║              Welcome to JARVIS Workspace Initialization            ║
║                                                                    ║
║  This ritual sets up your personal AI assistant's identity and    ║
║  preferences. Your answers will be stored in the workspace        ║
║  and in the runtime configuration.                                ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
""".strip()


def run_bootstrap_ritual(workspace: Path) -> dict[str, str | bool]:
    """Interactive three-beat bootstrap ritual.

    Returns:
        dict with keys: agent_name, agent_soul, minimal_plugins
    """
    print(_RITUAL_HEADER)
    print()

    # Beat 1: Ask for agent name
    agent_name = _beat_1_agent_name()

    # Beat 2: Ask for soul/vibe
    agent_soul = _beat_2_agent_soul()

    # Beat 3: Ask for plugin preference
    minimal_plugins = _beat_3_plugin_preference()

    return {
        "agent_name": agent_name,
        "agent_soul": agent_soul,
        "minimal_plugins": minimal_plugins,
    }


def _beat_1_agent_name() -> str:
    """First beat: ask for agent name."""
    print("BEAT 1: Agent Identity")
    print("─" * 70)
    print("What would you like to call your AI assistant?")
    print("(default: JARVIS, max 32 characters)")
    print()

    while True:
        response = input("Agent name: ").strip()
        if not response:
            response = "JARVIS"
        if len(response) > 32:
            print(f"  ✗ Name too long (max 32 chars). You entered: {len(response)}")
            continue
        # Allow alphanumeric, spaces, hyphens, underscores
        if all(c.isalnum() or c in " -_" for c in response):
            break
        print("  ✗ Use only letters, numbers, spaces, hyphens, or underscores.")

    print(f"  ✓ Agent name set to: {response}")
    print()
    return response


def _beat_2_agent_soul() -> str:
    """Second beat: ask for soul/vibe (short personality)."""
    print("BEAT 2: Voice & Tone")
    print("─" * 70)
    print("Describe your assistant's voice and tone (1–2 sentences).")
    print("Examples:")
    print("  • Formal, professional, English butler — yes, sir.")
    print("  • Casual, friendly, witty — let's ship it!")
    print("  • Concise, technical, no fluff — understood.")
    print()

    soul = input("Agent soul: ").strip()
    if not soul:
        soul = "Formal and concise, with dry humor."

    print(f"  ✓ Soul set to: {soul}")
    print()
    return soul


def _beat_3_plugin_preference() -> bool:
    """Third beat: ask for plugin preference (minimal vs. convenient)."""
    print("BEAT 3: Plugin Preference")
    print("─" * 70)
    print("Which plugin set would you like?")
    print()
    print("  (1) Minimal — core only (fast, lean)")
    print("  (2) Convenient — recommended set (feature-rich)")
    print()

    while True:
        response = input("Choice (1 or 2): ").strip()
        if response in ("1", "2"):
            minimal = response == "1"
            break
        print("  ✗ Please enter 1 or 2.")

    choice_str = "Minimal" if minimal else "Convenient"
    print(f"  ✓ Plugin set: {choice_str}")
    print()
    return minimal


def persist_bootstrap_to_identity_files(
    workspace: Path, ritual_result: dict[str, str | bool]
) -> None:
    """Write bootstrap choices to IDENTITY.md and SOUL.md in workspace root.

    These are the workspace-side persistent identity files that override
    starter templates.
    """
    agent_name = ritual_result["agent_name"]
    agent_soul = ritual_result["agent_soul"]

    # Update IDENTITY.md
    identity_path = workspace / "IDENTITY.md"
    identity_content = f"""# Identity

{agent_name} is a personal AI assistant. The operator is referred to
by name by default. {agent_name}:

- Speaks as described in SOUL.md.
- Never claims to have done something it hasn't.
- Calls tools when needed; asks when blocked.
- Logs every action to the HUD log.

Workspace: {workspace}
Configured: true
""".strip()
    identity_path.write_text(identity_content + "\n", encoding="utf-8")

    # Update SOUL.md
    soul_path = workspace / "SOUL.md"
    soul_content = f"""# Soul

{agent_name}'s voice:

{agent_soul}

If you change this file, the operator will hear the new voice in the
next session.
""".strip()
    soul_path.write_text(soul_content + "\n", encoding="utf-8")


def persist_bootstrap_to_config(
    config: JarvisConfig,
    ritual_result: dict[str, str | bool],
) -> JarvisConfig:
    """Persist bootstrap choices to config object.

    Returns a new JarvisConfig with agent identity set and workspace_configured=True.
    """
    agent_name = ritual_result["agent_name"]
    agent_soul = ritual_result["agent_soul"]

    new_agent = replace(
        config.agent,
        name=agent_name,
        soul=agent_soul,
        workspace_configured=True,
    )
    return replace(config, agent=new_agent)


__all__ = [
    "run_bootstrap_ritual",
    "persist_bootstrap_to_identity_files",
    "persist_bootstrap_to_config",
]
