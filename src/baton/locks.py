"""Run leases (§10.2): which Director may change a run right now.

A lease is a run-log event, so it travels with the run through git and
coordinates *sequential* handoff between Directors and machines. Defaults
(§18 #5): one hour, renewed on activity; a takeover needs a reason, and the
owner's approval for it is required by the director skill, not here.

* A lease is identified by ``(director_id, branch)``: a run lives on one
  branch at a time, so the same Director on another branch does not hold it.
* Mutating calls ``ensure`` the lease: a free or expired lease is claimed, the
  caller's own lease is renewed once more than half its term has passed, and
  an unexpired lease held by anyone else refuses with ``LeaseHeld``.
* Leases are bookkeeping, legal after a run ends; the runtime releases the
  lease when a run completes or is abandoned.

Events (``data``): ``lease_claimed`` / ``lease_taken_over``
``{director_id, harness, host, branch, expires_at}`` (a takeover adds
``from_director_id`` and ``reason``); ``lease_renewed {director_id,
expires_at}``; ``lease_released {director_id}``.
"""

from __future__ import annotations

import getpass
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Event
from .packet import EngineError
from .store import RunLog, format_ts

DIRECTOR_ID = re.compile(r"^[A-Za-z0-9._@+-]{1,128}$")


class LeaseHeld(EngineError):
    """Another Director holds the run's lease (CLI exit code 3)."""

    def __init__(self, message: str, lease: Lease):
        super().__init__("lease.held", message)
        self.lease = lease


@dataclass(frozen=True)
class Director:
    """Who is calling: the identity a lease is held under."""

    id: str
    harness: str = "cli"
    host: str = ""

    @classmethod
    def current(cls, director_id: str | None = None, harness: str | None = None) -> Director:
        did = director_id or os.environ.get("BATON_DIRECTOR") or f"{_user()}@{socket.gethostname()}"
        did = re.sub(r"[^A-Za-z0-9._@+-]", "_", did)[:128]
        return cls(did, harness or os.environ.get("BATON_HARNESS") or "cli", socket.gethostname())

    @property
    def actor(self) -> str:
        return f"director:{self.id}"


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - no login name in some containers
        return "director"


@dataclass(frozen=True)
class Lease:
    director_id: str
    harness: str | None
    host: str | None
    branch: str | None
    expires_at: str
    since_seq: int  # when this holder's term (claim or last renewal) started
    renewed_at: str  # ts of that event

    def expired(self, now: datetime) -> bool:
        return format_ts(now) >= self.expires_at

    def held_by(self, director: Director, branch: str | None) -> bool:
        return self.director_id == director.id and self.branch == branch

    def describe(self) -> str:
        where = f" on branch {self.branch}" if self.branch else ""
        return f"{self.director_id} ({self.harness or '?'} on {self.host or '?'}){where} until {self.expires_at}"


def current(events: list[Event]) -> Lease | None:
    """The run's lease as of its last event (expired or not), or None if released / never claimed."""
    lease: Lease | None = None
    for ev in events:
        d = ev.data
        if ev.type in ("lease_claimed", "lease_taken_over"):
            lease = Lease(d["director_id"], d.get("harness"), d.get("host"), d.get("branch"), d["expires_at"], ev.seq, ev.ts)
        elif ev.type == "lease_renewed" and lease is not None:
            lease = Lease(lease.director_id, lease.harness, lease.host, lease.branch, d["expires_at"], ev.seq, ev.ts)
        elif ev.type == "lease_released":
            lease = None
    return lease


def history(events: list[Event]) -> list[Event]:
    return [e for e in events if e.type.startswith("lease_")]


class Leases:
    """Lease operations on one run log."""

    def __init__(self, log: RunLog, director: Director, branch: str | None, minutes: int):
        self.log = log
        self.director = director
        self.branch = branch
        self.term = timedelta(minutes=minutes)

    def _now(self) -> datetime:
        return self.log.clock()

    def _expiry(self) -> str:
        return format_ts(self._now() + self.term)

    def _claim_data(self) -> dict[str, object]:
        return {
            "director_id": self.director.id,
            "harness": self.director.harness,
            "host": self.director.host,
            "branch": self.branch,
            "expires_at": self._expiry(),
        }

    def current(self) -> Lease | None:
        return current(self.log.events())

    def ensure(self) -> Lease:
        """Hold the lease before a mutating call: claim if free, renew if due, refuse if held elsewhere."""
        lease = self.current()
        now = self._now()
        if lease is None or lease.expired(now):
            data = self._claim_data()
            if lease is not None:
                data["previous"] = {"director_id": lease.director_id, "expired_at": lease.expires_at}
            self.log.append("lease_claimed", actor=self.director.actor, data=data)
            return self.current()  # type: ignore[return-value]
        if not lease.held_by(self.director, self.branch):
            raise LeaseHeld(f"run {self.log.run_id} is leased to {lease.describe()}", lease)
        term_start = datetime.fromisoformat(lease.renewed_at.replace("Z", "+00:00"))
        if now - term_start >= self.term / 2:
            self.log.append("lease_renewed", actor=self.director.actor, data={"director_id": self.director.id, "expires_at": self._expiry()})
            return self.current()  # type: ignore[return-value]
        return lease

    def take_over(self, reason: str) -> Lease:
        """Take the lease from its holder. The director skill requires the owner's approval first."""
        if not reason.strip():
            raise EngineError("lease.reason_required", "a takeover needs a reason")
        lease = self.current()
        if lease is None or lease.expired(self._now()) or lease.held_by(self.director, self.branch):
            return self.ensure()
        data = {**self._claim_data(), "from_director_id": lease.director_id, "from_branch": lease.branch, "reason": reason}
        self.log.append("lease_taken_over", actor=self.director.actor, data=data)
        return self.current()  # type: ignore[return-value]

    def release(self, *, actor: str | None = None) -> bool:
        """Release the caller's lease. False if there was none to release."""
        lease = self.current()
        if lease is None:
            return False
        if actor is None and not lease.held_by(self.director, self.branch) and not lease.expired(self._now()):
            raise LeaseHeld(f"run {self.log.run_id} is leased to {lease.describe()}; only its holder can release it", lease)
        self.log.append("lease_released", actor=actor or self.director.actor, data={"director_id": lease.director_id})
        return True
