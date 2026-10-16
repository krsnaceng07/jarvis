"""Zalo personal account session and credentials model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ZaloUserSession:
    imei: str = ""
    cookie: str = ""
    user_id: str = ""
    logged_in: bool = False

    def is_authenticated(self) -> bool:
        return bool(self.cookie and self.imei)
