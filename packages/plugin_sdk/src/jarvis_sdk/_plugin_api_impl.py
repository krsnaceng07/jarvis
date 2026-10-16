"""Internal PluginApi implementation split from api.py to satisfy max-line limits."""

from __future__ import annotations

from ._plugin_api_init import PluginApiInit
from ._plugin_api_registration_a import PluginApiRegistrationsA
from ._plugin_api_registration_b import PluginApiRegistrationsB
from ._plugin_api_registration_c import PluginApiRegistrationsC
from ._plugin_api_readback import PluginApiReadback


class PluginApi(
    PluginApiRegistrationsA,
    PluginApiRegistrationsB,
    PluginApiRegistrationsC,
    PluginApiReadback,
    PluginApiInit,
):
    """Internal PluginApi implementation built from split helper mixins.

    MRO: Mixin registrars first (so their ``self._tools`` etc. references
    resolve against the accumulators set up by ``PluginApiInit.__init__``),
    then ``PluginApiInit`` last so its ``__init__`` is inherited and the
    concrete class can be instantiated with ``PluginApi(ctx)``.
    """
