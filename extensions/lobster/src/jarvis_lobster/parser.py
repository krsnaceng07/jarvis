"""Parser for Lobster pipelines.

Mirrors parser.ts. Handles inline `A | B` pipelines and
YAML/JSON workflow files.
"""

from __future__ import annotations

import json
import os
import shlex
from typing import Any, Dict, List

import yaml


def parse_inline_pipeline(pipeline_str: str) -> List[Dict[str, Any]]:
    """Parse an inline pipeline string like `cmd --arg 1 | cmd2`."""
    stages = []
    # Basic pipe splitting. Does not handle quoted pipes for now.
    parts = pipeline_str.split("|")
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        tokens = shlex.split(part)
        if not tokens:
            continue
        command_name = tokens[0]
        args = {}
        positional = []

        idx = 1
        while idx < len(tokens):
            token = tokens[idx]
            if token.startswith("--"):
                key = token[2:]
                # Check if next token is a value or another flag
                if idx + 1 < len(tokens) and not tokens[idx + 1].startswith("--"):
                    args[key] = tokens[idx + 1]
                    idx += 2
                else:
                    args[key] = True
                    idx += 1
            else:
                positional.append(token)
                idx += 1

        if positional:
            args["_"] = positional

        stages.append(
            {
                "name": command_name,
                "args": args,
                "raw": part,
            }
        )
    return stages


def load_pipeline_file(filepath: str, cwd: str) -> Dict[str, Any]:
    """Load a .lobster workflow file (YAML or JSON)."""
    full_path = os.path.join(cwd, filepath)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Pipeline file not found: {filepath}")

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    if filepath.endswith(".json"):
        return json.loads(content)
    else:
        return yaml.safe_load(content)


def resolve_args(workflow: Dict[str, Any], provided_args: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve workflow arguments against defaults."""
    resolved = {}
    workflow_args = workflow.get("args", {})
    for key, spec in workflow_args.items():
        if key in provided_args:
            resolved[key] = provided_args[key]
        elif "default" in spec:
            resolved[key] = spec["default"]
        else:
            raise ValueError(f"Missing required workflow argument: {key}")
    return resolved


def parse_pipeline(pipeline: str, cwd: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse a pipeline string or file.

    Returns (stages, resolved_args)
    """
    if pipeline.endswith((".lobster", ".yaml", ".yml", ".json")):
        workflow = load_pipeline_file(pipeline, cwd)
        # We will map `steps` to stages
        stages = []
        for step in workflow.get("steps", []):
            cmd_str = step.get("command", "")
            if not cmd_str:
                continue
            # For simplicity, we parse the command string using our inline parser
            # and merge the explicit `env`, `stdin`, `condition` into the stage.
            parsed_cmd = parse_inline_pipeline(cmd_str)[0]
            stage = {
                "name": parsed_cmd["name"],
                "args": parsed_cmd["args"],
                "raw": cmd_str,
                "id": step.get("id"),
                "stdin": step.get("stdin"),
                "env": step.get("env", {}),
                "condition": step.get("condition"),
                "approval": step.get("approval"),
            }
            stages.append(stage)
        return stages, {}
    else:
        return parse_inline_pipeline(pipeline), {}
