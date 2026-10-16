from typing import Any, Dict
from .render import (
    preload_diff_html_before_after,
    preload_diff_html_patch,
    parse_patch_files,
    DiffRenderInputError,
)
from .browser import PlaywrightDiffScreenshotter
from .store import DiffArtifactStore


def normalize_diff_input(params: Dict[str, Any]) -> Dict[str, Any]:
    patch = params.get("patch", "").strip() if params.get("patch") else None
    before = params.get("before")
    after = params.get("after")

    if patch:
        if before is not None or after is not None:
            raise ValueError("Provide either patch or before/after input, not both.")
        title = params.get("title", "").strip() if params.get("title") else None
        return {"kind": "patch", "patch": patch, "title": title}

    if before is None or after is None:
        raise ValueError("Provide patch or both before and after text.")

    path = params.get("path")
    lang = params.get("lang")
    title = params.get("title")

    return {
        "kind": "before_after",
        "before": before,
        "after": after,
        "path": path,
        "lang": lang,
        "title": title,
    }


async def execute_diffs_tool(
    params: Dict[str, Any], context: Any, store: DiffArtifactStore
) -> Dict[str, Any]:
    try:
        input_data = normalize_diff_input(params)
    except ValueError as e:
        return {"content": [{"type": "text", "text": str(e)}], "details": {"error": str(e)}}

    mode = params.get("mode", "both")
    theme = params.get("theme", "dark")
    layout = params.get("layout", "unified")

    if input_data["kind"] == "before_after" and input_data["before"] == input_data["after"]:
        return {
            "content": [
                {"type": "text", "text": "Before and after are identical — no changes to render."}
            ],
            "details": {"changed": False},
        }

    render_options = {
        "themeType": theme,
        "diffStyle": layout,
        "expandUnchanged": params.get("expandUnchanged", False),
        "disableLineNumbers": False,
        "disableBackground": False,
    }

    try:
        if input_data["kind"] == "before_after":
            old_file = {
                "content": input_data["before"],
                "path": input_data.get("path", ""),
                "lang": input_data.get("lang", ""),
            }
            new_file = {
                "content": input_data["after"],
                "path": input_data.get("path", ""),
                "lang": input_data.get("lang", ""),
            }
            html = await preload_diff_html_before_after(old_file, new_file, render_options)
        else:
            files = await parse_patch_files(input_data["patch"])
            # Assuming first file from patch for simplicity or pass whole array if supported
            # preloadDiffHTML_patch in worker handles fileDiff array or object
            html = await preload_diff_html_patch(files, render_options)
    except DiffRenderInputError as e:
        return {
            "content": [{"type": "text", "text": f"Diff render error: {e}"}],
            "details": {"error": str(e)},
        }

    # Create Artifact
    artifact = await store.create_artifact(
        html=html,
        title=input_data.get("title"),
        input_kind=input_data["kind"],
        ttl_ms=params.get("ttlSeconds", 1800) * 1000,
    )

    viewer_url = f"http://localhost:7433{artifact['viewerPath']}"

    if mode == "view":
        return {
            "content": [{"type": "text", "text": f"Diff viewer ready.\n{viewer_url}"}],
            "details": {"changed": True, "artifactId": artifact["id"], "viewerUrl": viewer_url},
        }

    # Generate Image/PDF
    format_type = params.get("fileFormat", "png")

    screenshotter = PlaywrightDiffScreenshotter()

    file_artifact = await store.create_standalone_file_artifact(
        format=format_type, ttl_ms=params.get("ttlSeconds", 1800) * 1000
    )
    try:
        await screenshotter.screenshot_html(
            html=html, output_path=file_artifact["filePath"], theme=theme, image_format=format_type
        )
        await store.complete_file_artifact(file_artifact["id"])
    except Exception as e:
        await store.delete_file_artifact(file_artifact["id"])
        if mode == "both":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Diff viewer ready.\n{viewer_url}\nFile rendering failed: {e}",
                    }
                ],
                "details": {
                    "changed": True,
                    "artifactId": artifact["id"],
                    "viewerUrl": viewer_url,
                    "fileError": str(e),
                },
            }
        return {
            "content": [{"type": "text", "text": f"File rendering failed: {e}"}],
            "details": {"error": str(e)},
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Diff viewer: {viewer_url}\nDiff {format_type.upper()} generated at: {file_artifact['filePath']}\nUse the `message` tool with `path` or `filePath` to send this file.",
            }
        ],
        "details": {
            "changed": True,
            "artifactId": artifact["id"],
            "viewerUrl": viewer_url,
            "filePath": file_artifact["filePath"],
            "path": file_artifact["filePath"],
            "fileFormat": format_type,
        },
    }


def register_diffs_tool(api: Any, store: DiffArtifactStore) -> None:
    api.register_tool(
        name="diffs",
        description="Create a read-only diff viewer from before/after text or a unified patch. Returns a gateway viewer URL for canvas use and can also render the same diff to a PNG or PDF.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "before": {"type": "STRING", "description": "Original text content."},
                "after": {"type": "STRING", "description": "Updated text content."},
                "patch": {"type": "STRING", "description": "Unified diff or patch text."},
                "path": {"type": "STRING", "description": "Display path for before/after input."},
                "lang": {
                    "type": "STRING",
                    "description": "Optional language override for before/after input.",
                },
                "title": {"type": "STRING", "description": "Optional title for the rendered diff."},
                "mode": {
                    "type": "STRING",
                    "description": "Output mode: view, file, image (deprecated alias for file), or both. Default: both.",
                },
                "theme": {"type": "STRING", "description": "Viewer theme. Default: dark."},
                "layout": {"type": "STRING", "description": "Diff layout. Default: unified."},
                "fileQuality": {
                    "type": "STRING",
                    "description": "File quality preset: standard, hq, or print.",
                },
                "fileFormat": {
                    "type": "STRING",
                    "description": "Rendered file format: png or pdf.",
                },
                "fileScale": {
                    "type": "NUMBER",
                    "description": "Optional rendered-file device scale factor override (1-4).",
                },
                "fileMaxWidth": {
                    "type": "NUMBER",
                    "description": "Optional rendered-file max width in CSS pixels (640-2400).",
                },
                "expandUnchanged": {
                    "type": "BOOLEAN",
                    "description": "Expand unchanged sections instead of collapsing them.",
                },
                "ttlSeconds": {
                    "type": "NUMBER",
                    "description": "Artifact lifetime in seconds. Default: 1800.",
                },
                "baseUrl": {
                    "type": "STRING",
                    "description": "Optional gateway base URL override used when building the viewer URL.",
                },
            },
        },
        execute=lambda params: execute_diffs_tool(params, None, store),
    )
