"""JARVIS Gateway WS protocol schema — request, response, and event shapes.

Every frame exchanged over the JARVIS Gateway WebSocket uses one of these shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# ── RPC method enum ────────────────────────────────────────────────────


class RPCMethod(str, Enum):
    """Known gateway RPC method names."""

    # Sessions
    SESSIONS_CREATE = "sessions.create"
    SESSIONS_LIST = "sessions.list"
    SESSIONS_GET = "sessions.get"
    SESSIONS_RESOLVE = "sessions.resolve"
    SESSIONS_SEND = "sessions.send"
    SESSIONS_ABORT = "sessions.abort"
    SESSIONS_PATCH = "sessions.patch"
    SESSIONS_PATCH_MANY = "sessions.patchMany"
    SESSIONS_RESET = "sessions.reset"
    SESSIONS_DELETE = "sessions.delete"
    SESSIONS_RECOVER = "sessions.recover"
    SESSIONS_DISPATCH = "sessions.dispatch"
    SESSIONS_RECLAIM = "sessions.reclaim"
    SESSIONS_MOVE = "sessions.move"
    SESSIONS_COMPACT = "sessions.compact"
    SESSIONS_USAGE = "sessions.usage"
    SESSIONS_SEARCH = "sessions.search"
    SESSIONS_CLEANUP = "sessions.cleanup"
    SESSIONS_PREVIEW = "sessions.preview"
    SESSIONS_DESCRIBE = "sessions.describe"
    SESSIONS_ASSIGN_OWNER = "sessions.assignOwner"
    SESSIONS_FILES_GET = "sessions.files.get"
    SESSIONS_FILES_SET = "sessions.files.set"
    SESSIONS_FILES_LIST = "sessions.files.list"
    SESSIONS_FILES_REVEAL = "sessions.files.reveal"
    SESSIONS_DIFF = "sessions.diff"
    SESSIONS_BRANCHES_LIST = "sessions.branches.list"
    SESSIONS_BRANCHES_SWITCH = "sessions.branches.switch"
    SESSIONS_FORK = "sessions.fork"
    SESSIONS_REWIND = "sessions.rewind"
    SESSIONS_MEMBERS_LIST = "sessions.members.list"
    SESSIONS_MEMBERS_ADD = "sessions.members.add"
    SESSIONS_MEMBERS_REMOVE = "sessions.members.remove"
    SESSIONS_PUBLIC_SHARE_SET = "sessions.publicShare.set"
    SESSIONS_VISIBILITY_SET = "sessions.visibility.set"
    SESSIONS_COMPANION_ASK = "sessions.companion.ask"
    SESSIONS_COMPANION_RESET = "sessions.companion.reset"
    SESSIONS_COMPANION_STATE = "sessions.companion.state"
    SESSIONS_OBSERVER_VISIBILITY = "sessions.observer.visibility"
    SESSIONS_GROUPS_LIST = "sessions.groups.list"
    SESSIONS_GROUPS_DEFAULTS = "sessions.groups.defaults"
    SESSIONS_GROUPS_PUT = "sessions.groups.put"
    SESSIONS_GROUPS_RENAME = "sessions.groups.rename"
    SESSIONS_GROUPS_UPDATE = "sessions.groups.update"
    SESSIONS_GROUPS_DELETE = "sessions.groups.delete"
    SESSIONS_CATALOG_LIST = "sessions.catalog.list"
    SESSIONS_CATALOG_READ = "sessions.catalog.read"
    SESSIONS_CATALOG_CONTINUE = "sessions.catalog.continue"
    SESSIONS_CATALOG_ARCHIVE = "sessions.catalog.archive"
    SESSIONS_CATALOG_START_TERMINAL = "sessions.catalog.startTerminal"

    # Agents
    AGENTS_LIST = "agents.list"
    AGENTS_CREATE = "agents.create"
    AGENTS_UPDATE = "agents.update"
    AGENTS_DELETE = "agents.delete"
    AGENTS_FILES_LIST = "agents.files.list"
    AGENTS_FILES_GET = "agents.files.get"
    AGENTS_FILES_SET = "agents.files.set"
    AGENTS_WORKSPACE_LIST = "agents.workspace.list"
    AGENTS_WORKSPACE_GET = "agents.workspace.get"
    AGENTS_RUN = "agents.run"
    AGENTS_ABORT = "agents.abort"
    AGENT_DISPATCH = "agent.dispatch"
    AGENT_REACT = "agent.react"
    AGENT_MESSAGE = "agent.message"
    AGENT_ASKUSER = "agent.askUser"
    AGENT_IDENTITY = "agent.identity"

    # Conversations
    CONVERSATION_LIST = "conversation.list"
    CONVERSATION_SEND = "conversation.send"
    CONVERSATION_TURN = "conversation.turn"
    CONVERSATION_TURN_CANCEL = "conversation.turn.cancel"

    # Chat
    CHAT_SEND = "chat.send"
    CHAT_HISTORY = "chat.history"
    CHAT_STARTUP = "chat.startup"
    CHAT_METADATA = "chat.metadata"
    CHAT_INJECT = "chat.inject"
    CHAT_TOOL_TITLES = "chat.toolTitles"

    # Channels
    CHANNELS_STATUS = "channels.status"
    CHANNELS_PAIRING_LIST = "channels.pairing.list"
    CHANNELS_PAIRING_APPROVE = "channels.pairing.approve"
    CHANNELS_PAIRING_DISMISS = "channels.pairing.dismiss"
    CHANNELS_START = "channels.start"
    CHANNELS_STOP = "channels.stop"
    CHANNELS_LOGOUT = "channels.logout"
    CHANNELS_SEND = "channels.send"

    # Models
    MODELS_LIST = "models.list"
    MODELS_PROBE = "models.probe"
    MODELS_AUTH_STATUS = "models.auth.status"
    MODELS_AUTH_ORDER_SET = "models.auth.order.set"
    MODELS_AUTH_LOGOUT = "models.auth.logout"

    # Skills
    SKILLS_STATUS = "skills.status"
    SKILLS_INSTALL = "skills.install"
    SKILLS_SEARCH = "skills.search"
    SKILLS_DETAIL = "skills.detail"
    SKILLS_UPDATE = "skills.update"
    SKILLS_CURATOR_ACTION = "skills.curator.action"
    SKILLS_CURATOR_STATUS = "skills.curator.status"
    SKILLS_PROPOSALS_LIST = "skills.proposals.list"
    SKILLS_PROPOSAL_INSPECT = "skills.proposal.inspect"
    SKILLS_PROPOSAL_CREATE = "skills.proposal.create"
    SKILLS_PROPOSAL_UPDATE = "skills.proposal.update"
    SKILLS_PROPOSAL_REVISE = "skills.proposal.revise"
    SKILLS_PROPOSAL_REQUEST_REVISION = "skills.proposal.requestRevision"
    SKILLS_PROPOSAL_DECISION = "skills.proposal.decision"
    SKILLS_PROPOSAL_ACTION = "skills.proposal.action"
    SKILLS_PROPOSAL_EVALUATE = "skills.proposal.evaluate"
    SKILLS_PROPOSAL_EVENTS_LIST = "skills.proposal.events.list"
    SKILLS_SECURITY_VERDICTS = "skills.securityVerdicts"
    SKILLS_SKILL_CARD = "skills.skillCard"
    SKILLS_UPLOAD_BEGIN = "skills.upload.begin"
    SKILLS_UPLOAD_CHUNK = "skills.upload.chunk"
    SKILLS_UPLOAD_COMMIT = "skills.upload.commit"

    # Tools
    TOOLS_CATALOG = "tools.catalog"
    TOOLS_EFFECTIVE = "tools.effective"
    TOOLS_INVOKE = "tools.invoke"
    TOOLS_GITHUB_STATUS = "tools.github.status"
    TOOLS_GITHUB_CONFIGURE = "tools.github.configure"
    TOOLS_GITHUB_AUTHORIZE_START = "tools.github.authorize.start"
    TOOLS_GITHUB_AUTHORIZE_POLL = "tools.github.authorize.poll"
    TOOLS_GITHUB_AUTHORIZE_CANCEL = "tools.github.authorize.cancel"

    # Nodes
    NODE_LIST = "node.list"
    NODE_PAIR_LIST = "node.pair.list"
    NODE_PAIR_APPROVE = "node.pair.approve"
    NODE_PAIR_REJECT = "node.pair.reject"
    NODE_PAIR_REMOVE = "node.pair.remove"
    NODE_PLUGIN_TOOLS_UPDATE = "node.pluginTools.update"
    NODE_SKILLS_UPDATE = "node.skills.update"
    NODE_PENDING_ACK = "node.pending.ack"
    NODE_PENDING_DRAIN = "node.pending.drain"
    NODE_PENDING_ENQUEUE = "node.pending.enqueue"
    NODE_INVOKE = "node.invoke"
    NODE_INVOKE_PROGRESS = "node.invoke.progress"

    # Environments & Desktop
    ENVIRONMENTS_LIST = "environments.list"
    ENVIRONMENTS_CREATE = "environments.create"
    ENVIRONMENTS_DESTROY = "environments.destroy"
    ENVIRONMENTS_STATUS = "environments.status"
    DESKTOP_OBSERVE = "desktop.observe"
    DESKTOP_LAUNCH = "desktop.launch"

    # Terminal
    TERMINAL_OPEN = "terminal.open"
    TERMINAL_INPUT = "terminal.input"
    TERMINAL_RESIZE = "terminal.resize"
    TERMINAL_CLOSE = "terminal.close"
    TERMINAL_ATTACH = "terminal.attach"
    TERMINAL_LIST = "terminal.list"
    TERMINAL_UPLOAD = "terminal.upload"

    # Cron
    CRON_LIST = "cron.list"
    CRON_STATUS = "cron.status"
    CRON_GET = "cron.get"
    CRON_ADD = "cron.add"
    CRON_UPDATE = "cron.update"
    CRON_REMOVE = "cron.remove"
    CRON_RUN = "cron.run"
    CRON_RUNS = "cron.runs"
    CRON_SCRATCH_GET = "cron.scratch.get"
    CRON_SCRATCH_SET = "cron.scratch.set"

    # Approvals & Exec Approvals
    APPROVAL_GET = "approval.get"
    APPROVAL_HISTORY = "approval.history"
    APPROVAL_RESOLVE = "approval.resolve"
    EXEC_APPROVALS_GET = "exec.approvals.get"
    EXEC_APPROVALS_SET = "exec.approvals.set"
    EXEC_APPROVAL_GET = "exec.approval.get"
    EXEC_APPROVAL_REQUEST = "exec.approval.request"
    EXEC_APPROVAL_RESOLVE = "exec.approval.resolve"
    EXEC_APPROVALS_REQUEST = "exec.approvals.request"
    EXEC_APPROVALS_RESPOND = "exec.approvals.respond"

    # Questions
    QUESTION_GET = "question.get"
    QUESTION_LIST = "question.list"
    QUESTION_REQUEST = "question.request"
    QUESTION_WAIT_ANSWER = "question.waitAnswer"
    QUESTION_RESOLVE = "question.resolve"

    # Secrets
    SECRETS_STORE_LIST = "secrets.store.list"
    SECRETS_STORE_SET = "secrets.store.set"
    SECRETS_STORE_DELETE = "secrets.store.delete"

    # Config
    CONFIG_GET = "config.get"
    CONFIG_SET = "config.set"
    CONFIG_APPLY = "config.apply"
    CONFIG_PATCH = "config.patch"
    CONFIG_SCHEMA = "config.schema"
    CONFIG_SCHEMA_LOOKUP = "config.schema.lookup"

    # Plugins
    PLUGINS_LIST = "plugins.list"

    # Admin & System
    ADMIN_RELOAD = "admin.reload"
    ADMIN_STATUS = "admin.status"
    SYSTEM_INFO = "system.info"
    SYSTEM_CHANGES_LIST = "system.changes.list"
    SYSTEM_AGENT_CHAT = "system.agent.chat"
    SYSTEM_AGENT_CHAT_HISTORY = "system.agent.chat.history"
    SYSTEM_AGENT_SETUP_DETECT = "system.agent.setup.detect"
    SYSTEM_AGENT_SETUP_VERIFY = "system.agent.setup.verify"
    SYSTEM_AGENT_SETUP_ACTIVATE = "system.agent.setup.activate"
    SYSTEM_AGENT_SETUP_ACTIVATE_START = "system.agent.setup.activate.start"
    SYSTEM_AGENT_SETUP_AUTH_START = "system.agent.setup.auth.start"

    # Wizard & Updates
    WIZARD_START = "wizard.start"
    WIZARD_NEXT = "wizard.next"
    WIZARD_CANCEL = "wizard.cancel"
    WIZARD_STATUS = "wizard.status"
    UPDATE_STATUS = "update.status"
    UPDATE_HOLD = "update.hold"
    UPDATE_REPORT = "update.report"
    UPDATE_RUNS_GET = "update.runs.get"
    UPDATE_RUNS_LIST = "update.runs.list"

    # Logs, Talk & Transcripts
    LOGS_TAIL = "logs.tail"
    TALK_CATALOG = "talk.catalog"
    TALK_CONFIG = "talk.config"
    TALK_SPEAK = "talk.speak"
    TTS_SPEAK = "tts.speak"
    FS_LIST_DIR = "fs.listDir"
    PROJECTS_LIST = "projects.list"
    PROJECTS_REGISTER = "projects.register"
    PROJECTS_ADD = "projects.add"
    PROJECTS_SEARCH_REMOTE = "projects.searchRemote"
    PROJECTS_REMOVE = "projects.remove"
    WORKTREES_LIST = "worktrees.list"
    WORKTREES_CREATE = "worktrees.create"
    WORKTREES_REMOVE = "worktrees.remove"
    WORKTREES_RESTORE = "worktrees.restore"
    WORKTREES_GC = "worktrees.gc"
    WORKTREES_BRANCHES = "worktrees.branches"
    TRANSCRIPTS_LIST = "transcripts.list"
    TRANSCRIPTS_GET = "transcripts.get"


# ── Request ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """A Gateway protocol request frame (OpenClaw format).

    Format: { "type": "req", "id": "...", "method": "...", "params": {...} }
    """

    method: str
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    type: Literal["req"] = "req"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "req", "method": self.method, "id": self.id, "params": self.params}


# ── Error ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayError:
    """A Gateway protocol error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d

    # ── Convenience constructors ──────────────────────────────────────

    @classmethod
    def parse_error(cls, detail: str = "") -> GatewayError:
        return cls(-32700, "Parse error", detail or None)

    @classmethod
    def invalid_request(cls, detail: str = "") -> GatewayError:
        return cls(-32600, "Invalid request", detail or None)

    @classmethod
    def method_not_found(cls, method: str = "") -> GatewayError:
        return cls(-32601, f"Method not found: {method}", method or None)

    @classmethod
    def invalid_params(cls, detail: str = "") -> GatewayError:
        return cls(-32602, "Invalid params", detail or None)

    @classmethod
    def internal_error(cls, detail: str = "") -> GatewayError:
        return cls(-32603, "Internal error", detail or None)

    @classmethod
    def auth_error(cls, detail: str = "") -> GatewayError:
        return cls(-32001, "Unauthorized", detail or None)


# ── Response ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    """A Gateway protocol response frame (OpenClaw format).

    Format: { "type": "res", "id": "...", "ok": bool, "payload": any, "error": GatewayError | None }
    """

    id: str = ""
    payload: Any = None
    error: GatewayError | None = None
    type: Literal["res"] = "res"

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "res", "id": self.id, "ok": self.ok}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["payload"] = self.payload
        return d


# ── Event ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    """A Gateway protocol event frame (OpenClaw format).

    Format: { "type": "event", "event": "...", "payload": any, "seq": int | None, "stateVersion": int | None }
    """

    event: str
    payload: Any
    seq: int | None = None
    stateVersion: int | None = None
    type: Literal["event"] = "event"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "event", "event": self.event, "payload": self.payload}
        if self.seq is not None:
            d["seq"] = self.seq
        if self.stateVersion is not None:
            d["stateVersion"] = self.stateVersion
        return d


# JSON-RPC 2.0 compatibility shapes expected by tests and clients


class EventMethod(str, Enum):
    """Known Gateway JSON-RPC 2.0 outbound event notification methods."""

    AGENT_DRAFT = "event.agent.draft"
    CHANNEL_MESSAGE = "event.channel.message"
    GATEWAY_EVENT = "gateway.event"
    TASK_COMPLETED = "event.task.completed"


@dataclass(frozen=True, slots=True)
class RPCRequest:
    """JSON-RPC 2.0 request shape used by Gateway RPC handler tests.

    Format: { "jsonrpc": "2.0", "method": "...", "id": "...", "params": {...} }
    """

    method: str
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": self.method, "id": self.id, "params": self.params}


@dataclass(frozen=True, slots=True)
class RPCResponse:
    """JSON-RPC 2.0 response shape.

    Format: { "jsonrpc": "2.0", "id": "...", "result": any } or { "jsonrpc": "2.0", "id": "...", "error": {...} }
    """

    id: str = ""
    result: Any | None = None
    error: GatewayError | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d


@dataclass(frozen=True, slots=True)
class RPCEvent:
    """JSON-RPC 2.0 event (notification) shape.

    Format: { "jsonrpc": "2.0", "method": "...", "params": {...} }
    """

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": self.method, "params": self.params}


# Backwards RPC aliases
RPCError = GatewayError

__all__ = [
    "EventMethod",
    "GatewayError",
    "GatewayEvent",
    "GatewayRequest",
    "GatewayResponse",
    "RPCError",
    "RPCEvent",
    "RPCMethod",
    "RPCRequest",
    "RPCResponse",
]
