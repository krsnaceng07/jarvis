"""Visitor access service and grant lifecycle.

OpenClaw parity: mirrors extensions/visitor-access/src/visitors.ts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import re
import time
from typing import Any, Callable, TypedDict
import urllib.parse
import urllib.request
import urllib.error

from .cloudflare import VisitorPolicyClient
from .config import VisitorAccessConfig
from .errors import VisitorAccessError

DAY_MS = 86_400_000
EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
GITHUB_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")


class VisitorGrant(TypedDict, total=False):
    email: str
    githubLogin: str | None
    invitedVia: str | None
    createdAt: int
    expiresAt: int | None


def expiry_text(expires_at: int | None) -> str:
    if expires_at is None:
        return "never (explicit forever grant)"
    dt = datetime.fromtimestamp(expires_at / 1000.0, tz=UTC)
    return dt.isoformat()


class VisitorAccessService:
    def __init__(
        self,
        config: VisitorAccessConfig,
        policy_client: VisitorPolicyClient,
        store: dict[str, VisitorGrant] | None = None,
        logger: Any = None,
        github_fetcher: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.config = config
        self.policy = policy_client
        self.store = store if store is not None else {}
        self.logger = logger
        self.github_fetcher = github_fetcher
        self._lock = asyncio.Lock()

    async def wait_for_idle(self) -> None:
        pass

    async def _resolve_email(self, input_data: dict[str, Any]) -> str:
        em = input_data.get("email")
        if em and isinstance(em, str) and em.strip():
            em_clean = em.strip().lower()
            if not EMAIL_RE.match(em_clean):
                raise VisitorAccessError(f"Invalid email: {em}")
            return em_clean

        gh = input_data.get("github")
        if not gh or not isinstance(gh, str) or not gh.strip():
            raise VisitorAccessError("Provide an email or GitHub login.")

        gh_clean = gh.strip().lstrip("@").lower()
        if not GITHUB_RE.match(gh_clean):
            raise VisitorAccessError(f"Invalid GitHub username: {gh}")

        if self.github_fetcher:
            data = self.github_fetcher(gh_clean)
            resolved = data.get("email")
            if resolved and isinstance(resolved, str) and resolved.strip():
                return resolved.strip().lower()
            raise VisitorAccessError(
                f"GitHub user @{gh_clean} has no public email address; invite by explicit email."
            )

        # Default GitHub API lookup
        url = f"https://api.github.com/users/{urllib.parse.quote(gh_clean)}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "JARVIS-visitor-access",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                email_val = data.get("email")
                if email_val and isinstance(email_val, str) and email_val.strip():
                    return email_val.strip().lower()
                raise VisitorAccessError(
                    f"GitHub user @{gh_clean} has no public email address; invite by explicit email."
                )
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise VisitorAccessError(f"GitHub user @{gh_clean} does not exist.") from err
            raise VisitorAccessError(f"GitHub API error ({err.code}) for @{gh_clean}") from err
        except VisitorAccessError:
            raise
        except Exception as err:
            raise VisitorAccessError(f"Failed to lookup GitHub user @{gh_clean}: {err}") from err

    async def invite(self, raw_input: dict[str, Any], invited_via: str | None = None) -> str:
        async with self._lock:
            email = await self._resolve_email(raw_input)
            gh_login = str(raw_input.get("github", "")).lstrip("@").lower() or None
            forever = bool(raw_input.get("forever"))
            days = raw_input.get("days")

            if forever and days is not None:
                raise VisitorAccessError("Cannot combine 'forever' with explicit 'days'.")

            now_ms = int(time.time() * 1000)
            if forever:
                expires_at = None
            elif days is not None:
                try:
                    d_int = int(days)
                    if d_int < 1 or d_int > 3650:
                        raise VisitorAccessError("days must be between 1 and 3650")
                    expires_at = now_ms + d_int * DAY_MS
                except ValueError as err:
                    raise VisitorAccessError("days must be an integer between 1 and 3650") from err
            elif self.config["defaultTtlDays"] is not None and self.config["defaultTtlDays"] > 0:
                expires_at = now_ms + self.config["defaultTtlDays"] * DAY_MS
            else:
                raise VisitorAccessError("Explicit duration in days or forever: true is required.")

            if email not in self.store and len(self.store) >= self.config["maxVisitors"]:
                raise VisitorAccessError(
                    f"Maximum visitor limit ({self.config['maxVisitors']}) reached. Revoke unused grants before inviting."
                )

            # Update Cloudflare Access policy
            await self.policy.update(lambda current: [*current, email])

            grant: VisitorGrant = {
                "email": email,
                "githubLogin": gh_login,
                "invitedVia": invited_via,
                "createdAt": now_ms,
                "expiresAt": expires_at,
            }
            self.store[email] = grant
            return f"Granted visitor access to {email} until {expiry_text(expires_at)}."

    async def revoke(self, raw_input: dict[str, Any]) -> str:
        async with self._lock:
            gh = (
                str(raw_input.get("github", "")).lstrip("@").lower()
                if raw_input.get("github")
                else None
            )
            em = str(raw_input.get("email", "")).strip().lower() if raw_input.get("email") else None

            revoked_emails: list[str] = []
            if em:
                revoked_emails.append(em)
            if gh:
                for k, grant in list(self.store.items()):
                    if grant.get("githubLogin") == gh:
                        revoked_emails.append(k)

            if not revoked_emails:
                raise VisitorAccessError("Provide an email or GitHub login to revoke.")

            revoked_set = set(revoked_emails)
            await self.policy.update(lambda current: [e for e in current if e not in revoked_set])

            for e in revoked_emails:
                self.store.pop(e, None)

            return f"Revoked visitor access for: {', '.join(sorted(revoked_set))}."

    async def list(self) -> str:
        async with self._lock:
            pol = await self.policy.read()
            pol_emails = set(pol["emails"] if pol else [])

            lines: list[str] = [
                f"Managed Policy: {self.config['policyName']} ({len(self.store)} recorded grants)"
            ]
            now_ms = int(time.time() * 1000)

            for email, grant in sorted(self.store.items()):
                status = "active"
                exp = grant.get("expiresAt")
                if exp is not None and exp < now_ms:
                    status = "expired"
                in_cf = "in policy" if email in pol_emails else "MISSING from policy"
                gh_str = f" (@{grant['githubLogin']})" if grant.get("githubLogin") else ""
                lines.append(f"- {email}{gh_str}: {status} ({in_cf}), expires {expiry_text(exp)}")

            # Unmanaged emails in Cloudflare policy
            unmanaged = [e for e in pol_emails if e not in self.store]
            if unmanaged:
                lines.append("\nUnmanaged emails in Cloudflare policy (not tracked locally):")
                for u in sorted(unmanaged):
                    lines.append(f"- {u} (unmanaged)")

            return "\n".join(lines)

    async def sweep(self) -> int:
        async with self._lock:
            now_ms = int(time.time() * 1000)
            expired_emails = [
                e
                for e, g in self.store.items()
                if g.get("expiresAt") is not None and g["expiresAt"] <= now_ms  # type: ignore[operator]
            ]
            if not expired_emails:
                return 0

            expired_set = set(expired_emails)
            await self.policy.update(lambda current: [e for e in current if e not in expired_set])
            for e in expired_emails:
                self.store.pop(e, None)

            if self.logger and hasattr(self.logger, "info"):
                self.logger.info(
                    f"visitor-access: swept {len(expired_emails)} expired visitor grant(s)"
                )
            return len(expired_emails)
