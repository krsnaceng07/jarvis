"""jarvis.application_automation — Continuous application control, tab affinity & UI automation."""

from .action_verifier import ActionEffect, ActionVerificationResult
from .active_tab_tracker import ActiveTabTracker, TrackedTab, detect_application_type_from_url
from .application_session_manager import ApplicationSessionManager
from .contextual_resolver import ContextualResolver, ResolvedAction
from .providers.youtube_provider import YouTubeProvider
from .state_machine import ApplicationStateMachine, StateTransition
from .tools.youtube_tools import dispatch_youtube_tool

__all__ = [
    "ActionEffect",
    "ActionVerificationResult",
    "ActiveTabTracker",
    "ApplicationSessionManager",
    "ApplicationStateMachine",
    "ContextualResolver",
    "ResolvedAction",
    "StateTransition",
    "TrackedTab",
    "YouTubeProvider",
    "detect_application_type_from_url",
    "dispatch_youtube_tool",
]

