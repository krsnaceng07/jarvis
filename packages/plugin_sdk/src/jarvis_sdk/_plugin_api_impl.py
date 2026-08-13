"""Internal PluginApi implementation split from api.py to satisfy max-line limits."""
from __future__ import annotations

from ._plugin_api_init import PluginApiInit
from ._plugin_api_registration_a import PluginApiRegistrationsA
from ._plugin_api_registration_b import PluginApiRegistrationsB
from ._plugin_api_registration_c import PluginApiRegistrationsC
from ._plugin_api_readback import PluginApiReadback


class PluginApi(
    PluginApiInit,
    PluginApiRegistrationsA,
    PluginApiRegistrationsB,
    PluginApiRegistrationsC,
    PluginApiReadback,
):
    """Internal PluginApi implementation built from split helper mixins."""
    pass
