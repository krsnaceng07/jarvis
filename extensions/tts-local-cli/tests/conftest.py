"""Conftest for the tts-local-cli test suite.

The extension directory uses a hyphen (``tts-local-cli``)
which is not a valid Python identifier, so the import
path cannot reach the package via
``extensions.tts_local_cli.lib``. This conftest ensures
``extensions/tts-local-cli/`` is on ``sys.path`` for every
test collection so ``from lib.speech_provider import ...``
resolves to ``extensions/tts-local-cli/lib/speech_provider.py``.
"""
from __future__ import annotations

import os
import sys

_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)
