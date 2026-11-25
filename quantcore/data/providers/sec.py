"""Existing official SEC connection, GET only with contact/rate limits and no host fallback."""

import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values


class SECUnavailable(RuntimeError):
    pass


class SECData:
    def __init__(self, root, transport=None):
        agent = os.getenv("SEC_USER_AGENT") or dotenv_values(Path(root) / ".env").get("SEC_USER_AGENT")
        if not agent or "@" not in agent:
            raise SECUnavailable("SEC_USER_AGENT is not configured")
        self.client = httpx.Client(
            timeout=35, headers={"User-Agent": agent}, follow_redirects=False, transport=transport
        )
        self.next_request = 0.0

    def get(self, url):
        parsed = urlsplit(url)
        allowed = (
            parsed.scheme == "https" and not parsed.query and not parsed.fragment and not parsed.username
        )
        allowed &= (
            parsed.netloc == "data.sec.gov"
            and bool(
                re.fullmatch(r"/(submissions/CIK\d{10}|api/xbrl/companyfacts/CIK\d{10})\.json", parsed.path)
            )
        ) or (
            parsed.netloc == "www.sec.gov"
            and bool(
                re.fullmatch(
                    r"/Archives/edgar/data/\d+/\d{18}/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", parsed.path
                )
            )
        )
        if not allowed or ".." in parsed.path:
            raise ValueError("SEC endpoint outside the approved read-only scope")
        time.sleep(max(0, self.next_request - time.monotonic()))
        self.next_request = time.monotonic() + 0.3
        try:
            response = self.client.get(url)
        except httpx.TransportError:
            raise SECUnavailable("SEC network request failed") from None
        if response.status_code != 200:
            raise SECUnavailable(f"SEC HTTP {response.status_code}; no entitlement/access bypass")
        if len(response.content) > 30 * 1024 * 1024:
            raise SECUnavailable("SEC document exceeds the bounded size limit")
        return response.content

    def close(self):
        self.client.close()
