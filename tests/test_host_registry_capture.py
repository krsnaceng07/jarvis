"""Host registry integration tests.

Verify that the host `create_plugin_registry` factory exposes a `createApi`
factory whose registrar wrappers update the host registry state when
invoked by a plugin API view.
"""
from __future__ import annotations

from pathlib import Path

from src.plugins.registry import create_plugin_registry


def test_create_api_register_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p1", "name": "P1", "kind": "plugin"}
    api = create_api(rec, {"config": {}})

    provider = {"id": "prov1", "name": "Provider One"}
    # Call via the legacy CamelCase registrar callable exposed on the view
    api["registerProvider"](provider)

    providers = state["registry"]["providers"]
    assert any(isinstance(p, dict) and p.get("id") == "prov1" for p in providers)


def test_create_api_register_tool_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p2", "name": "P2", "kind": "plugin"}
    api = create_api(rec, {})

    tool = {"name": "toolA"}
    api["registerTool"](tool, {"name": "toolA"})

    tools = state["registry"]["tools"]
    assert any(isinstance(t, dict) and t.get("ownerPluginId") == "p2" and "toolA" in t.get("names", []) for t in tools)


def test_create_api_register_channel_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p4", "name": "P4", "kind": "plugin", "origin": "user", "source": "src"}
    api = create_api(rec, {})

    channel = {"id": "chan1", "kind": "chat"}
    api["registerChannel"](channel)

    channels = state["registry"]["channels"]
    assert any(
        isinstance(c, dict)
        and c.get("pluginId") == "p4"
        and c.get("pluginName") == "P4"
        and c.get("id") == "chan1"
        and c.get("kind") == "chat"
        for c in channels
    )


def test_create_api_register_http_route_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p5", "name": "P5", "kind": "plugin"}
    api = create_api(rec, {})

    route = {"path": "/api/test", "handler": lambda req: None}
    api["registerHttpRoute"](route)

    routes = state["registry"]["httpRoutes"]
    assert any(
        isinstance(r, dict)
        and r.get("_owner_id") == "p5"
        and r.get("path") == "/api/test"
        for r in routes
    )


def test_plugin_api_register_http_handler_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p5b", "name": "P5B", "kind": "plugin"}
    api = create_api(rec, {})

    route = {"path": "/api/handler", "handler": lambda req: None}
    api["pluginApi"].register_http_handler(route)

    routes = state["registry"]["httpRoutes"]
    assert any(
        isinstance(r, dict)
        and r.get("_owner_id") == "p5b"
        and r.get("path") == "/api/handler"
        for r in routes
    )


def test_create_api_register_model_catalog_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p6", "name": "P6", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "cat1", "name": "Catalog One"}
    api["registerModelCatalogProvider"](provider)

    providers = state["registry"]["modelCatalogProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("provider", {}).get("id") == "cat1"
        and p.get("pluginId") == "p6"
        for p in providers
    )


def test_create_api_options_populates_plugin_context() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    logger = object()
    rec = {"id": "p3", "name": "P3", "kind": "plugin"}
    api = create_api(rec, {"config": {"foo": "bar"}, "logger": logger, "dataDir": "/tmp/data", "workspaceDir": "/tmp/workspace"})

    assert api["pluginApi"].ctx.logger is logger
    assert api["pluginApi"].ctx.data_dir == Path("/tmp/data")
    assert api["pluginApi"].ctx.workspace == Path("/tmp/workspace")
    assert api["logger"] is logger
    assert api["config"] == {"foo": "bar"}


def test_plugin_api_register_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p7", "name": "P7", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "prov2", "name": "Provider Two"}
    api["pluginApi"].register_provider(provider)

    providers = state["registry"]["providers"]
    assert any(isinstance(p, dict) and p.get("id") == "prov2" for p in providers)


def test_plugin_api_register_tool_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p11", "name": "P11", "kind": "plugin"}
    api = create_api(rec, {})

    tool = {"name": "toolB"}
    api["pluginApi"].register_tool(tool, {"name": "toolB"})

    tools = state["registry"]["tools"]
    assert any(isinstance(t, dict) and t.get("ownerPluginId") == "p11" and "toolB" in t.get("names", []) for t in tools)


def test_plugin_api_register_http_route_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p12", "name": "P12", "kind": "plugin"}
    api = create_api(rec, {})

    route = {"path": "/api/health", "handler": lambda req: None}
    api["pluginApi"].register_http_route(route)

    routes = state["registry"]["httpRoutes"]
    assert any(isinstance(r, dict) and r.get("_owner_id") == "p12" and r.get("path") == "/api/health" for r in routes)


def test_plugin_api_register_channel_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p14", "name": "P14", "kind": "plugin", "origin": "user", "source": "src"}
    api = create_api(rec, {})

    channel = {"id": "chan2", "kind": "chat"}
    api["pluginApi"].register_channel(channel)

    channels = state["registry"]["channels"]
    assert any(
        isinstance(c, dict)
        and c.get("pluginId") == "p14"
        and c.get("pluginName") == "P14"
        and c.get("id") == "chan2"
        and c.get("kind") == "chat"
        for c in channels
    )


def test_create_api_register_cli_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p23", "name": "P23", "kind": "plugin"}
    api = create_api(rec, {})

    api["registerCli"]({"id": "cli-foo"})

    entries = state["registry"]["cliRegistrars"]
    assert any(isinstance(entry, dict) and entry.get("ownerPluginId") == "p23" and entry.get("id") == "cli-foo" for entry in entries)


def test_create_api_register_session_action_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p24a", "name": "P24A", "kind": "plugin"}
    api = create_api(rec, {})

    action = {"type": "complete", "payload": {"done": True}}
    api["registerSessionAction"](action)

    actions = state["registry"]["sessionActions"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p24a"
        and entry.get("type") == "complete"
        for entry in actions
    )


def test_create_api_register_agent_event_subscription_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p24b", "name": "P24B", "kind": "plugin"}
    api = create_api(rec, {})

    subscription = {"event": "message.created", "handler": lambda *_args, **_kwargs: None}
    api["registerAgentEventSubscription"](subscription)

    subscriptions = state["registry"]["agentEventSubscriptions"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p24b"
        and entry.get("event") == "message.created"
        for entry in subscriptions
    )


def test_create_api_register_control_ui_descriptor_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p24c", "name": "P24C", "kind": "plugin"}
    api = create_api(rec, {})

    descriptor = {"id": "ui-1", "label": "Test UI"}
    api["registerControlUiDescriptor"](descriptor)

    descriptors = state["registry"]["controlUiDescriptors"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p24c"
        and entry.get("id") == "ui-1"
        for entry in descriptors
    )


def test_create_api_register_trusted_tool_policy_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p24d", "name": "P24D", "kind": "plugin"}
    api = create_api(rec, {})

    policy = {"tool": "toolA", "trusted": True}
    api["registerTrustedToolPolicy"](policy)

    policies = state["registry"]["trustedToolPolicies"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p24d"
        and entry.get("tool") == "toolA"
        for entry in policies
    )


def test_plugin_api_register_hosted_media_resolver_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p21", "name": "P21", "kind": "plugin"}
    api = create_api(rec, {})

    resolver = {"id": "media2", "resolve": lambda *_args, **_kwargs: None}
    api["pluginApi"].register_hosted_media_resolver(resolver)

    resolvers = state["registry"]["hostedMediaResolvers"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p21"
        and r.get("id") == "media2"
        and callable(r.get("resolve"))
        for r in resolvers
    )


def test_plugin_api_register_session_scheduler_job_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p24", "name": "P24", "kind": "plugin"}
    api = create_api(rec, {})

    job = {"id": "job1", "schedule": "*/5 * * * *"}
    api["pluginApi"].register_session_scheduler_job(job)

    jobs = state["registry"]["sessionSchedulerJobs"]
    assert any(
        isinstance(j, dict)
        and j.get("ownerPluginId") == "p24"
        and j.get("id") == "job1"
        and j.get("schedule") == "*/5 * * * *"
        for j in jobs
    )


def test_plugin_api_register_node_host_command_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p25", "name": "P25", "kind": "plugin"}
    api = create_api(rec, {})

    cmd = {"name": "host-cmd", "handler": lambda *_args, **_kwargs: None}
    api["pluginApi"].register_node_host_command(cmd)

    entries = state["registry"]["nodeHostCommands"]
    assert any(
        isinstance(e, dict)
        and e.get("ownerPluginId") == "p25"
        and e.get("name") == "host-cmd"
        for e in entries
    )


def test_plugin_api_register_agent_harness_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p26", "name": "P26", "kind": "plugin"}
    api = create_api(rec, {})

    harness = {"id": "harness-1", "type": "sandbox"}
    api["pluginApi"].register_agent_harness(harness)

    harnesses = state["registry"]["agentHarnesses"]
    assert any(
        isinstance(h, dict)
        and h.get("id") == "harness-1"
        and h.get("type") == "sandbox"
        for h in harnesses
    )


def test_plugin_api_register_session_extension_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p27", "name": "P27", "kind": "plugin"}
    api = create_api(rec, {})

    ext = {"name": "session-ext"}
    api["pluginApi"].register_session_extension(ext)

    extensions = state["registry"]["sessionExtensions"]
    assert any(
        isinstance(e, dict)
        and e.get("ownerPluginId") == "p27"
        and e.get("name") == "session-ext"
        for e in extensions
    )


def test_plugin_api_register_memory_prompt_section_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p28", "name": "P28", "kind": "plugin"}
    api = create_api(rec, {})

    section = {"section": "mem-segment"}
    print('pluginApi method', api["pluginApi"].register_memory_prompt_section)
    api["pluginApi"].register_memory_prompt_section(section)

    metadata = state["registry"]["toolMetadata"]
    print('toolMetadata', metadata)
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p28"
        and m.get("section") == "mem-segment"
        for m in metadata
    )


def test_plugin_api_register_tool_metadata_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p41", "name": "P41", "kind": "plugin"}
    api = create_api(rec, {})

    metadata_item = {"id": "meta1", "value": "data"}
    api["pluginApi"].register_tool_metadata(metadata_item)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p41"
        and m.get("id") == "meta1"
        for m in metadata
    )


def test_plugin_api_register_session_action_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p42", "name": "P42", "kind": "plugin"}
    api = create_api(rec, {})

    action = {"type": "complete", "payload": {"done": True}}
    api["pluginApi"].register_session_action(action)

    actions = state["registry"]["sessionActions"]
    assert any(
        isinstance(a, dict)
        and a.get("ownerPluginId") == "p42"
        and a.get("type") == "complete"
        for a in actions
    )


def test_plugin_api_register_agent_event_subscription_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p43", "name": "P43", "kind": "plugin"}
    api = create_api(rec, {})

    sub = {"event": "message.created", "handler": lambda *_args, **_kwargs: None}
    api["pluginApi"].register_agent_event_subscription(sub)

    subs = state["registry"]["agentEventSubscriptions"]
    assert any(
        isinstance(s, dict)
        and s.get("ownerPluginId") == "p43"
        and s.get("event") == "message.created"
        for s in subs
    )


def test_plugin_api_register_control_ui_descriptor_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p44", "name": "P44", "kind": "plugin"}
    api = create_api(rec, {})

    desc = {"id": "ui1", "label": "Test UI"}
    api["pluginApi"].register_control_ui_descriptor(desc)

    descriptors = state["registry"]["controlUiDescriptors"]
    assert any(
        isinstance(d, dict)
        and d.get("ownerPluginId") == "p44"
        and d.get("id") == "ui1"
        for d in descriptors
    )


def test_plugin_api_register_trusted_tool_policy_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p45", "name": "P45", "kind": "plugin"}
    api = create_api(rec, {})

    policy = {"tool": "toolA", "trusted": True}
    api["pluginApi"].register_trusted_tool_policy(policy)

    policies = state["registry"]["trustedToolPolicies"]
    assert any(
        isinstance(p, dict)
        and p.get("ownerPluginId") == "p45"
        and p.get("tool") == "toolA"
        for p in policies
    )


def test_plugin_api_register_mcp_server_connection_resolver_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p46", "name": "P46", "kind": "plugin"}
    api = create_api(rec, {})

    resolver = {"id": "conn1", "handler": lambda *_args, **_kwargs: None}
    api["pluginApi"].register_mcp_server_connection_resolver(resolver)

    resolvers = state["registry"]["mcpServerConnectionResolvers"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p46"
        and r.get("id") == "conn1"
        for r in resolvers
    )


def test_plugin_api_register_reload_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p47", "name": "P47", "kind": "plugin"}
    api = create_api(rec, {})

    reload_item = {"reason": "update"}
    api["pluginApi"].register_reload(reload_item)

    reloads = state["registry"]["reloads"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p47"
        and r.get("reason") == "update"
        for r in reloads
    )


def test_plugin_api_register_node_invoke_policy_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p48", "name": "P48", "kind": "plugin"}
    api = create_api(rec, {})

    policy = {"name": "invoke-policy"}
    api["pluginApi"].register_node_invoke_policy(policy)

    policies = state["registry"]["nodeInvokePolicies"]
    assert any(
        isinstance(p, dict)
        and p.get("ownerPluginId") == "p48"
        and p.get("name") == "invoke-policy"
        for p in policies
    )


def test_plugin_api_register_security_audit_collector_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p49", "name": "P49", "kind": "plugin"}
    api = create_api(rec, {})

    collector = {"id": "collector1"}
    api["pluginApi"].register_security_audit_collector(collector)

    collectors = state["registry"]["securityAuditCollectors"]
    assert any(
        isinstance(c, dict)
        and c.get("ownerPluginId") == "p49"
        and c.get("id") == "collector1"
        for c in collectors
    )


def test_plugin_api_register_session_catalog_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p50", "name": "P50", "kind": "plugin"}
    api = create_api(rec, {})

    catalog = {"id": "sc1"}
    api["pluginApi"].register_session_catalog(catalog)

    catalogs = state["registry"]["sessionCatalogs"]
    assert any(
        isinstance(c, dict)
        and c.get("ownerPluginId") == "p50"
        and c.get("id") == "sc1"
        for c in catalogs
    )


def test_plugin_api_register_text_transforms_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p51", "name": "P51", "kind": "plugin"}
    api = create_api(rec, {})

    transforms = [{"name": "upper"}]
    api["pluginApi"].register_text_transforms(transforms)

    out = state["registry"]["textTransforms"]
    assert any(
        isinstance(t, dict)
        and t.get("ownerPluginId") == "p51"
        and isinstance(t.get("item"), list)
        for t in out
    )


def test_create_api_register_text_transform_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p51b", "name": "P51B", "kind": "plugin"}
    api = create_api(rec, {})

    transform = {"id": "upper", "handler": lambda value: value.upper()}
    api["registerTextTransform"](transform)

    out = state["registry"]["textTransforms"]
    assert any(
        isinstance(t, dict)
        and t.get("ownerPluginId") == "p51b"
        and t.get("id") == "upper"
        for t in out
    )


def test_create_api_register_text_transforms_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p51c", "name": "P51C", "kind": "plugin"}
    api = create_api(rec, {})

    transforms = [{"id": "upper", "handler": lambda value: value.upper()}]
    api["registerTextTransforms"](transforms)

    out = state["registry"]["textTransforms"]
    assert any(
        isinstance(t, dict)
        and t.get("ownerPluginId") == "p51c"
        and isinstance(t.get("item"), list)
        for t in out
    )


def test_create_api_register_http_handler_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p5c", "name": "P5C", "kind": "plugin"}
    api = create_api(rec, {})

    route = {"path": "/api/handler-alias", "handler": lambda req: None}
    api["registerHttpHandler"](route)

    routes = state["registry"]["httpRoutes"]
    assert any(
        isinstance(r, dict)
        and r.get("_owner_id") == "p5c"
        and r.get("path") == "/api/handler-alias"
        for r in routes
    )


def test_create_api_register_cron_alias_forwards_to_plugin_api() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p100", "name": "P100", "kind": "plugin"}
    api = create_api(rec, {})

    job = {"id": "job-cron", "schedule": "0 * * * *", "handler": lambda *_args, **_kwargs: None}
    api["registerCron"](job)

    cron_jobs = state["registry"]["cronJobs"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p100"
        and entry.get("id") == "job-cron"
        and entry.get("schedule") == "0 * * * *"
        for entry in cron_jobs
    )


def test_create_api_register_doctor_contract_alias_forwards_to_plugin_api() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p101", "name": "P101", "kind": "plugin"}
    api = create_api(rec, {})

    contract = {"id": "doctor-a", "version": "1.0", "detect": lambda: False, "apply": lambda: None}
    api["registerDoctorContract"](contract)

    contracts = state["registry"]["doctorContracts"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p101"
        and entry.get("id") == "doctor-a"
        and entry.get("version") == "1.0"
        for entry in contracts
    )


def test_create_api_register_skill_alias_forwards_to_plugin_api() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p102", "name": "P102", "kind": "plugin"}
    api = create_api(rec, {})

    skill = {"name": "skill-a", "description": "A test skill"}
    api["registerSkill"](skill)

    skills = state["registry"]["skills"]
    assert any(
        isinstance(entry, dict)
        and entry.get("ownerPluginId") == "p102"
        and entry.get("name") == "skill-a"
        and entry.get("description") == "A test skill"
        for entry in skills
    )


def test_plugin_api_register_interactive_handler_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p52", "name": "P52", "kind": "plugin"}
    api = create_api(rec, {})

    handler = lambda *_args, **_kwargs: None
    api["pluginApi"].register_interactive_handler(handler)

    handlers = state["registry"]["interactiveHandlers"]
    assert any(
        isinstance(h, dict)
        and h.get("ownerPluginId") == "p52"
        and h.get("item") == handler
        for h in handlers
    )


def test_plugin_api_register_conversation_binding_resolved_handler_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p53", "name": "P53", "kind": "plugin"}
    api = create_api(rec, {})

    handler = lambda *_args, **_kwargs: None
    api["pluginApi"].register_conversation_binding_resolved_handler(handler)

    handlers = state["registry"]["conversationBindingResolvedHandlers"]
    assert any(
        isinstance(h, dict)
        and h.get("ownerPluginId") == "p53"
        and h.get("item") == handler
        for h in handlers
    )


def test_plugin_api_register_compaction_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p54", "name": "P54", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "compaction-1"}
    api["pluginApi"].register_compaction_provider(provider)

    providers = state["registry"]["compactionProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("ownerPluginId") == "p54"
        and p.get("id") == "compaction-1"
        for p in providers
    )


def test_plugin_api_register_memory_prompt_supplement_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p55", "name": "P55", "kind": "plugin"}
    api = create_api(rec, {})

    supplement = lambda *_args, **_kwargs: None
    api["pluginApi"].register_memory_prompt_supplement(supplement)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p55"
        and m.get("item") is supplement
        for m in metadata
    )


def test_plugin_api_register_memory_runtime_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p56", "name": "P56", "kind": "plugin"}
    api = create_api(rec, {})

    runtime = {"id": "mem-runtime"}
    api["pluginApi"].register_memory_runtime(runtime)

    lifecycles = state["registry"]["runtimeLifecycles"]
    assert any(
        isinstance(l, dict)
        and l.get("ownerPluginId") == "p56"
        and l.get("id") == "mem-runtime"
        for l in lifecycles
    )


def test_plugin_api_register_memory_flush_plan_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p57", "name": "P57", "kind": "plugin"}
    api = create_api(rec, {})

    plan = {"id": "flush1"}
    api["pluginApi"].register_memory_flush_plan(plan)

    reloads = state["registry"]["reloads"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p57"
        and r.get("id") == "flush1"
        for r in reloads
    )


def test_plugin_api_register_memory_embedding_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {
        "id": "p58",
        "name": "P58",
        "kind": "memory",
    }
    api = create_api(rec, {})

    adapter = {"id": "mem-embed1", "name": "Memory Embed"}
    api["pluginApi"].register_memory_embedding_provider(adapter)

    providers = state["registry"]["memoryEmbeddingProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("pluginId") == "p58"
        and p.get("provider", {}).get("id") == "mem-embed1"
        for p in providers
    )


def test_create_api_register_memory_prompt_preparation_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p59", "name": "P59", "kind": "plugin"}
    api = create_api(rec, {})

    preparer = lambda *_args, **_kwargs: []
    api["registerMemoryPromptPreparation"](preparer)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p59"
        and m.get("item") is preparer
        for m in metadata
    )


def test_create_api_register_memory_corpus_supplement_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p60", "name": "P60", "kind": "plugin"}
    api = create_api(rec, {})

    supplement = {"id": "corpus1", "body": "memory"}
    api["registerMemoryCorpusSupplement"](supplement)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p60"
        and m.get("id") == "corpus1"
        for m in metadata
    )


def test_create_api_register_memory_prompt_section_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p61", "name": "P61", "kind": "plugin"}
    api = create_api(rec, {})

    section = {"section": "mem-segment"}
    api["registerMemoryPromptSection"](section)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p61"
        and m.get("section") == "mem-segment"
        for m in metadata
    )


def test_create_api_register_memory_prompt_supplement_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p62", "name": "P62", "kind": "plugin"}
    api = create_api(rec, {})

    supplement = lambda *_args, **_kwargs: None
    api["registerMemoryPromptSupplement"](supplement)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p62"
        and m.get("item") is supplement
        for m in metadata
    )


def test_create_api_register_memory_flush_plan_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p63", "name": "P63", "kind": "plugin"}
    api = create_api(rec, {})

    plan = {"id": "flush2"}
    api["registerMemoryFlushPlan"](plan)

    reloads = state["registry"]["reloads"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p63"
        and r.get("id") == "flush2"
        for r in reloads
    )


def test_create_api_register_memory_runtime_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p64", "name": "P64", "kind": "plugin"}
    api = create_api(rec, {})

    runtime = {"id": "runtime2"}
    api["registerMemoryRuntime"](runtime)

    lifecycles = state["registry"]["runtimeLifecycles"]
    assert any(
        isinstance(l, dict)
        and l.get("ownerPluginId") == "p64"
        and l.get("id") == "runtime2"
        for l in lifecycles
    )


def test_create_api_register_memory_embedding_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {
        "id": "p65",
        "name": "P65",
        "kind": "memory",
    }
    api = create_api(rec, {})

    adapter = {"id": "mem-embed2", "name": "Memory Embed"}
    api["registerMemoryEmbeddingProvider"](adapter)

    providers = state["registry"]["memoryEmbeddingProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("pluginId") == "p65"
        and p.get("provider", {}).get("id") == "mem-embed2"
        for p in providers
    )


def test_create_api_register_memory_capability_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p66", "name": "P66", "kind": "memory"}
    api = create_api(rec, {})

    capability = {"id": "cap2", "publicArtifacts": []}
    api["registerMemoryCapability"](capability)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p66"
        and m.get("id") == "cap2"
        for m in metadata
    )


def test_plugin_api_register_memory_capability_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p67", "name": "P67", "kind": "memory"}
    api = create_api(rec, {})

    capability = {"id": "cap3", "publicArtifacts": []}
    api["pluginApi"].register_memory_capability(capability)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p67"
        and m.get("id") == "cap3"
        for m in metadata
    )


def test_plugin_api_register_memory_prompt_preparation_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p62", "name": "P62", "kind": "plugin"}
    api = create_api(rec, {})

    preparer = lambda *_args, **_kwargs: []
    api["pluginApi"].register_memory_prompt_preparation(preparer)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p62"
        and m.get("item") is preparer
        for m in metadata
    )


def test_plugin_api_register_memory_corpus_supplement_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p63", "name": "P63", "kind": "plugin"}
    api = create_api(rec, {})

    supplement = {"id": "corpus2", "body": "memory"}
    api["pluginApi"].register_memory_corpus_supplement(supplement)

    metadata = state["registry"]["toolMetadata"]
    assert any(
        isinstance(m, dict)
        and m.get("ownerPluginId") == "p63"
        and m.get("id") == "corpus2"
        for m in metadata
    )


def test_plugin_api_register_embedding_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p22", "name": "P22", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "embed2", "name": "EmbedderTwo"}
    api["pluginApi"].register_embedding_provider(provider)

    providers = state["registry"]["embeddingProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("id") == "embed2"
        for p in providers
    )


def test_plugin_api_register_model_catalog_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p15", "name": "P15", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "cat2", "name": "Catalog Two"}
    api["pluginApi"].register_model_catalog_provider(provider)

    providers = state["registry"]["modelCatalogProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("provider", {}).get("id") == "cat2"
        and p.get("pluginId") == "p15"
        for p in providers
    )


def test_plugin_api_register_typed_hook_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p13", "name": "P13", "kind": "plugin"}
    api = create_api(rec, {})

    api["pluginApi"].register_typed_hook("validate", lambda *_args, **_kwargs: None)

    typed_hooks = state["registry"]["typedHooks"]
    assert any(
        isinstance(h, dict)
        and h.get("ownerPluginId") == "p13"
        and h.get("hookName") == "validate"
        for h in typed_hooks
    )


def test_create_api_register_gateway_method_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p16", "name": "P16", "kind": "plugin"}
    api = create_api(rec, {})

    method_desc = {"id": "method-a", "surface": "agent"}
    api["registerGatewayMethod"](method_desc)

    descriptors = state["registry"]["gatewayMethodDescriptors"]
    assert any(
        isinstance(d, dict)
        and d.get("ownerPluginId") == "p16"
        and d.get("id") == "method-a"
        for d in descriptors
    )


def test_plugin_api_register_command_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p17", "name": "P17", "kind": "plugin"}
    api = create_api(rec, {})

    api["pluginApi"].register_command({"name": "hello", "handler": lambda *_args, **_kwargs: None})

    commands = state["registry"]["commands"]
    assert any(
        isinstance(cmd, dict)
        and cmd.get("ownerPluginId") == "p17"
        and cmd.get("name") == "hello"
        for cmd in commands
    )


def test_plugin_api_register_context_engine_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p18", "name": "P18", "kind": "plugin"}
    api = create_api(rec, {})

    engine = {"id": "ctx-a", "factory": lambda: None}
    api["pluginApi"].register_context_engine(engine)

    lifecycles = state["registry"]["runtimeLifecycles"]
    assert any(
        isinstance(l, dict)
        and l.get("ownerPluginId") == "p18"
        and l.get("id") == "ctx-a"
        for l in lifecycles
    )


def test_create_api_register_worker_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p8", "name": "P8", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "worker1", "name": "Worker One"}
    api["registerWorkerProvider"](provider)

    workers = state["registry"]["workerProviders"]
    assert isinstance(workers, dict)
    assert "worker1" in workers
    assert workers["worker1"]["provider"]["id"] == "worker1"
    assert workers["worker1"]["ownerPluginId"] == "p8"


def test_create_api_register_hook_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p9", "name": "P9", "kind": "plugin"}
    api = create_api(rec, {})

    hook = {"name": "validate", "handler": lambda *_args, **_kwargs: None}
    api["registerHook"](hook)

    hooks = state["registry"]["hooks"]
    assert any(isinstance(h, dict) and h.get("ownerPluginId") == "p9" and h.get("hook") == hook for h in hooks)


def test_create_api_register_hosted_media_resolver_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p19", "name": "P19", "kind": "plugin"}
    api = create_api(rec, {})

    resolver = {"id": "media1", "resolve": lambda *_args, **_kwargs: None}
    api["registerHostedMediaResolver"](resolver)

    resolvers = state["registry"]["hostedMediaResolvers"]
    assert any(
        isinstance(r, dict)
        and r.get("ownerPluginId") == "p19"
        and r.get("id") == "media1"
        and callable(r.get("resolve"))
        for r in resolvers
    )


def test_create_api_register_embedding_provider_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p20", "name": "P20", "kind": "plugin"}
    api = create_api(rec, {})

    provider = {"id": "embed1", "name": "Embedder"}
    api["registerEmbeddingProvider"](provider)

    providers = state["registry"]["embeddingProviders"]
    assert any(
        isinstance(p, dict)
        and p.get("id") == "embed1"
        for p in providers
    )


def test_create_api_register_typed_hook_updates_host_registry() -> None:
    state = create_plugin_registry({"logger": None})
    create_api = state["createApi"]

    rec = {"id": "p10", "name": "P10", "kind": "plugin"}
    api = create_api(rec, {})

    api["registerTypedHook"](hook_name="validate", handler=lambda *_args, **_kwargs: None)

    typed_hooks = state["registry"]["typedHooks"]
    assert any(
        isinstance(h, dict)
        and h.get("ownerPluginId") == "p10"
        and h.get("hookName") == "validate"
        for h in typed_hooks
    )
