"""Cloudflare Access policy client for visitor-access.

OpenClaw parity: mirrors extensions/visitor-access/src/cloudflare.ts.
"""

from __future__ import annotations

import json
from typing import Any, Callable
import urllib.parse
import urllib.request
import urllib.error

from .config import VisitorAccessConfig
from .errors import VisitorAccessError


class VisitorPolicyClient:
    def __init__(
        self,
        config: VisitorAccessConfig,
        http_requester: Callable[..., Any] | None = None,
    ):
        self.config = config
        self.http_requester = http_requester
        acc_enc = urllib.parse.quote(config["accountId"], safe="")
        app_enc = urllib.parse.quote(config["appId"], safe="")
        self.policies_url = f"https://api.cloudflare.com/client/v4/accounts/{acc_enc}/access/apps/{app_enc}/policies"

    def _request(self, url: str, method: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.http_requester:
            return self.http_requester(url, method, data)

        headers = {
            "Authorization": f"Bearer {self.config['apiToken']}",
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-visitor-access",
        }
        body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))
                if not raw_json.get("success"):
                    raise VisitorAccessError(
                        f"Cloudflare API returned error: {raw_json.get('errors')}"
                    )
                return raw_json
        except urllib.error.HTTPError as err:
            err_msg = err.read().decode("utf-8", errors="replace")
            raise VisitorAccessError(f"Cloudflare API HTTP {err.code}: {err_msg}") from err
        except Exception as err:
            raise VisitorAccessError(f"Cloudflare API error: {err}") from err

    def read_policy(self) -> dict[str, Any] | None:
        """Find the managed policy by name across paginated results."""
        for page in range(1, 101):
            url = f"{self.policies_url}?page={page}&per_page=100"
            res = self._request(url, "GET")
            policies = res.get("result", [])
            if not isinstance(policies, list):
                raise VisitorAccessError("Cloudflare returned an invalid policy list")
            for pol in policies:
                if isinstance(pol, dict) and pol.get("name") == self.config["policyName"]:
                    return pol
            if len(policies) < 100:
                break
        return None

    async def read(self) -> dict[str, Any] | None:
        policy = self.read_policy()
        if not policy:
            return None
        include_rules = policy.get("include", [])
        emails: list[str] = []
        if isinstance(include_rules, list):
            for rule in include_rules:
                if isinstance(rule, dict) and "email" in rule and isinstance(rule["email"], dict):
                    em = rule["email"].get("email")
                    if em and isinstance(em, str):
                        emails.append(em.lower().strip())
        return {"id": policy.get("id", ""), "emails": list(dict.fromkeys(emails))}

    async def update(self, change_fn: Callable[[list[str]], list[str]]) -> list[str]:
        policy = self.read_policy()
        current_emails = []
        if policy:
            include_rules = policy.get("include", [])
            if isinstance(include_rules, list):
                for rule in include_rules:
                    if (
                        isinstance(rule, dict)
                        and "email" in rule
                        and isinstance(rule["email"], dict)
                    ):
                        em = rule["email"].get("email")
                        if em and isinstance(em, str):
                            current_emails.append(em.lower().strip())
        current_emails = list(dict.fromkeys(current_emails))

        new_emails = list(dict.fromkeys([e.lower().strip() for e in change_fn(current_emails)]))

        if len(new_emails) == len(current_emails) and set(new_emails) == set(current_emails):
            return new_emails

        if policy and len(new_emails) == 0:
            del_url = (
                f"{self.policies_url}/{urllib.parse.quote(str(policy.get('id', '')), safe='')}"
            )
            self._request(del_url, "DELETE")
            return new_emails

        payload: dict[str, Any] = {
            "name": self.config["policyName"],
            "decision": "allow",
            "include": [{"email": {"email": email}} for email in new_emails],
        }

        if policy:
            put_url = (
                f"{self.policies_url}/{urllib.parse.quote(str(policy.get('id', '')), safe='')}"
            )
            self._request(put_url, "PUT", payload)
        else:
            self._request(self.policies_url, "POST", payload)

        return new_emails
