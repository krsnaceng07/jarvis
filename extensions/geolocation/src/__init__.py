"""Geolocation package."""

from .config import (
    DEFAULT_ATTRIBUTION_TEXT,
    DEFAULT_ATTRIBUTION_URL,
    DEFAULT_DATABASE_URL,
    DEFAULT_REFRESH_DAYS,
    GeolocationSettings,
    expand_database_urls,
    resolve_geolocation_settings,
)
from .database_store import (
    GeolocationDatabase,
    GeolocationDatabaseStore,
    create_geolocation_database_store,
)
from .lookup import GeolocationResult, project_geolocation_record
from .lookup_route import (
    GeolocationLookupHandler,
    create_geolocation_lookup_handler,
    is_private_or_loopback_ip,
    is_valid_ip,
)

__all__ = [
    "DEFAULT_ATTRIBUTION_TEXT",
    "DEFAULT_ATTRIBUTION_URL",
    "DEFAULT_DATABASE_URL",
    "DEFAULT_REFRESH_DAYS",
    "GeolocationDatabase",
    "GeolocationDatabaseStore",
    "GeolocationLookupHandler",
    "GeolocationResult",
    "GeolocationSettings",
    "create_geolocation_database_store",
    "create_geolocation_lookup_handler",
    "expand_database_urls",
    "is_private_or_loopback_ip",
    "is_valid_ip",
    "project_geolocation_record",
    "resolve_geolocation_settings",
]
