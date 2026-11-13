"""Pacote video-extractor: motor de extração (sem dependências de UI)."""

from .engine import *  # noqa: F401,F403
from .engine import __all__ as _engine_all

__all__ = list(_engine_all)
__version__ = "0.1.0"
