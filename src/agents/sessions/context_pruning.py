from typing import Any
import re

def _is_tool_result_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "toolResult"

def _get_tool_name(message: dict[str, Any]) -> str | None:
    return message.get("name")

def _get_text_length(content: str | list[dict[str, Any]]) -> int:
    if isinstance(content, str):
        return len(content)
    elif isinstance(content, list):
        return sum(len(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
    return 0

def _trim_text_content(content: str | list[dict[str, Any]], max_len: int = 3000) -> str | list[dict[str, Any]]:
    keep_len = max_len // 2
    if isinstance(content, str):
        if len(content) <= max_len:
            return content
        return content[:keep_len] + "\n...\n" + content[-keep_len:]
    elif isinstance(content, list):
        full_text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                full_text += block.get("text", "")
        
        if len(full_text) <= max_len:
            return content
        trimmed_text = full_text[:keep_len] + "\n...\n" + full_text[-keep_len:]
        return [{"type": "text", "text": trimmed_text}]
    return content

def _parse_ttl_to_seconds(ttl: str) -> float:
    if not ttl:
        return 0.0
    if ttl.endswith("h"):
        return float(ttl[:-1]) * 3600
    if ttl.endswith("m"):
        return float(ttl[:-1]) * 60
    if ttl.endswith("s"):
        return float(ttl[:-1])
    try:
        return float(ttl)
    except ValueError:
        return 300.0

def apply_context_pruning(
    messages: list[dict[str, Any]],
    prune_config: dict[str, Any] | None,
    last_pruned_time: float,
    current_time: float,
    max_context_window: int = 128000 * 4
) -> tuple[list[dict[str, Any]], float, bool]:
    modified = False
    
    # 1. Legacy image cleanup runs unconditionally
    completed_turns = 0
    image_protected_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        role = messages[i].get("role")
        if role in ("assistant", "user"):
            completed_turns += 1
            if completed_turns == 3:
                image_protected_idx = i
                break

    new_messages = list(messages)
    for i in range(image_protected_idx):
        msg = new_messages[i]
        content = msg.get("content")
        if isinstance(content, list):
            new_content = []
            msg_modified = False
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image":
                    new_content.append({"type": "text", "text": "[image data removed - already processed by model]"})
                    msg_modified = True
                elif isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if "[media attached:" in text or "[Image: source:" in text or "media://inbound/" in text:
                        text = re.sub(r'\[media attached:.*?\]', '[media reference removed - already processed by model]', text)
                        text = re.sub(r'\[Image: source:.*?\]', '[media reference removed - already processed by model]', text)
                        text = re.sub(r'media://inbound/\S+', '[media reference removed - already processed by model]', text)
                        new_content.append({"type": "text", "text": text})
                        msg_modified = True
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)
            if msg_modified:
                new_msg = dict(msg)
                new_msg["content"] = new_content
                new_messages[i] = new_msg
                modified = True
        elif isinstance(content, str):
            text = content
            if "[media attached:" in text or "[Image: source:" in text or "media://inbound/" in text:
                text = re.sub(r'\[media attached:.*?\]', '[media reference removed - already processed by model]', text)
                text = re.sub(r'\[Image: source:.*?\]', '[media reference removed - already processed by model]', text)
                text = re.sub(r'media://inbound/\S+', '[media reference removed - already processed by model]', text)
                new_msg = dict(msg)
                new_msg["content"] = text
                new_messages[i] = new_msg
                modified = True

    if not prune_config:
        return new_messages, last_pruned_time, modified
        
    mode = prune_config.get("mode", "off")
    if mode != "cache-ttl":
        return new_messages, last_pruned_time, modified
        
    ttl_str = prune_config.get("ttl", "5m")
    ttl_seconds = _parse_ttl_to_seconds(ttl_str)
    
    if current_time - last_pruned_time < ttl_seconds:
        return new_messages, last_pruned_time, modified
        
    total_chars = sum(_get_text_length(msg.get("content", "")) for msg in new_messages)
    if total_chars < max_context_window * 0.3:
        return new_messages, last_pruned_time, modified
        
    assistant_turns_seen = 0
    protected_end_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            assistant_turns_seen += 1
            if assistant_turns_seen == 3:
                protected_end_idx = i
                break
                
    protected_start_idx = 0
    for i in range(len(messages)):
        if messages[i].get("role") == "user":
            protected_start_idx = i
            break
            
    tools_allow = prune_config.get("tools", {}).get("allow") if prune_config.get("tools") else None
    tools_deny = prune_config.get("tools", {}).get("deny") if prune_config.get("tools") else None
    
    soft_trim_limit = 4000
    modified = False
    new_messages = []
    prunable_chars = 0
    
    for i, msg in enumerate(messages):
        if protected_start_idx <= i < protected_end_idx and _is_tool_result_message(msg):
            tool_name = _get_tool_name(msg)
            if tools_allow and tool_name not in tools_allow:
                new_messages.append(msg)
                continue
            if tools_deny and tool_name in tools_deny:
                new_messages.append(msg)
                continue
                
            content_len = _get_text_length(msg.get("content", ""))
            if content_len > soft_trim_limit:
                new_msg = dict(msg)
                new_msg["content"] = _trim_text_content(msg.get("content", ""), max_len=3000)
                new_messages.append(new_msg)
                modified = True
                prunable_chars += _get_text_length(new_msg["content"])
            else:
                new_messages.append(msg)
                prunable_chars += content_len
        else:
            new_messages.append(msg)
            
    hard_clear_enabled = prune_config.get("hardClear", {}).get("enabled", True) if prune_config.get("hardClear") else True
    if hard_clear_enabled:
        new_total_chars = sum(_get_text_length(msg.get("content", "")) for msg in new_messages)
        if new_total_chars >= max_context_window * 0.5 and prunable_chars >= 50000:
            placeholder = prune_config.get("hardClear", {}).get("placeholder", "[Old tool result content cleared]") if prune_config.get("hardClear") else "[Old tool result content cleared]"
            for i, msg in enumerate(new_messages):
                if protected_start_idx <= i < protected_end_idx and _is_tool_result_message(msg):
                    tool_name = _get_tool_name(msg)
                    if tools_allow and tool_name not in tools_allow:
                        continue
                    if tools_deny and tool_name in tools_deny:
                        continue
                    
                    new_msg = dict(msg)
                    if isinstance(new_msg["content"], str):
                        new_msg["content"] = placeholder
                    elif isinstance(new_msg["content"], list):
                        new_msg["content"] = [{"type": "text", "text": placeholder}]
                    new_messages[i] = new_msg
                    modified = True

    completed_turns = 0
    image_protected_idx = len(new_messages)
    for i in range(len(new_messages) - 1, -1, -1):
        role = new_messages[i].get("role")
        if role in ("assistant", "user"):
            completed_turns += 1
            if completed_turns == 3:
                image_protected_idx = i
                break

    for i in range(image_protected_idx):
        msg = new_messages[i]
        content = msg.get("content")
        if isinstance(content, list):
            new_content = []
            msg_modified = False
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image":
                    new_content.append({"type": "text", "text": "[image data removed - already processed by model]"})
                    msg_modified = True
                elif isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if "[media attached:" in text or "[Image: source:" in text or "media://inbound/" in text:
                        text = re.sub(r'\[media attached:.*?\]', '[media reference removed - already processed by model]', text)
                        text = re.sub(r'\[Image: source:.*?\]', '[media reference removed - already processed by model]', text)
                        text = re.sub(r'media://inbound/\S+', '[media reference removed - already processed by model]', text)
                        new_content.append({"type": "text", "text": text})
                        msg_modified = True
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)
            if msg_modified:
                new_msg = dict(msg)
                new_msg["content"] = new_content
                new_messages[i] = new_msg
                modified = True
        elif isinstance(content, str):
            text = content
            if "[media attached:" in text or "[Image: source:" in text or "media://inbound/" in text:
                text = re.sub(r'\[media attached:.*?\]', '[media reference removed - already processed by model]', text)
                text = re.sub(r'\[Image: source:.*?\]', '[media reference removed - already processed by model]', text)
                text = re.sub(r'media://inbound/\S+', '[media reference removed - already processed by model]', text)
                new_msg = dict(msg)
                new_msg["content"] = text
                new_messages[i] = new_msg
                modified = True

    if modified:
        return new_messages, current_time, True
        
    return new_messages, last_pruned_time, False
