"""What Baton learns about each model from real work: the track record, trials and their budget (§6.4, §8.4).

Decisions 0175, 0176, 0179 and 0182; change ``2026-11-model-assessment``.

* **Evidence identity (0179, item 5).** Evidence belongs to a model on a route: its canonical ``model_id``, adapter,
  provider, invocation identifier and endpoint (``route_key``). A route with no ``model_id`` (an alias) gets no key:
  it may be checked, but it is never a candidate and earns no standing. The harness version and the model's rating are
  kept with the evidence: a different harness version starts the record afresh when it is next written, and a different
  rating makes the old standing void at once (0182, item 2).
* **The record.** ``models:`` in ``$BATON_HOME/track-record.yaml``, beside the last-check records under ``profiles:``
  (``capability_check.py``), which stay as they were. Each route keeps totals by tier and kind (``check`` totals come
  from the last-check records; ``trial``, ``shadow`` and ``step`` here) and its recent outcomes. An outcome has an id
  (run, step path, attempt, kind), so recording the same intake twice records it once.
* **Standing (0176, item 5; 0182, items 2 and 3).** At a tier, from the counted trial and shadow outcomes there:
  ``put_back`` with ``put_back_after`` failures in the last ``window``; else ``proven`` after ``proven_after`` passes
  with no failure in the last ``window``; else ``candidate``. The owner may promote or put back by hand; evidence after
  that can still put a promoted route back. Proven changes no eligibility. Put back treats the model as one tier below
  that tier for routing until promoted (``routing.requirement_gaps``).
* **Trials (0179, items 1-3).** ``trial_candidate`` picks, for a step that qualifies, an eligible model other than the
  Director's choice that is not proven or put back at the step's tier, is free or cheaper than the choice, and fits the
  budget. The Director's choice is the fallback.
* **Budget (0179, item 4; 0182, item 4).** ``reserve`` claims a conservative estimate against the day's limit under a
  machine-wide lock; ``reconcile`` replaces it with the measured cost when the attempt ends. A paid route needs a price.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from .data import YamlError, load_yaml
from .locks import file_lock

#: Outcome kinds kept per route. ``check`` totals come from the last-check records.
KINDS = ("trial", "shadow", "step")
#: Kinds whose outcomes decide standing (0176, item 5).
STANDING_KINDS = ("trial", "shadow")
#: Recent outcomes kept per route.
KEEP = 100
SPEND_FILE = "assessment-spend.yaml"
SPEND_LOCK = ".assessment-spend.lock"
#: The estimate's assumptions (0179, item 4: conservative): a full context of input on each of a few calls, and a long reply.
ESTIMATE_CONTEXT_TOKENS = 200_000
ESTIMATE_CALLS = 4
ESTIMATE_OUTPUT_TOKENS = 16_000


class AssessmentError(Exception):
    pass


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def route_key(profile: Any) -> str | None:
    """The route's evidence key, or ``None`` for an alias, a person or a program (0179, item 5)."""
    if profile.adapter in ("manual", "program", "command") or not profile.model_id:
        return None
    endpoint = (profile.options or {}).get("base_url") or (profile.options or {}).get("api_base") or "-"
    return "|".join([profile.model_id, profile.adapter, profile.provider or "-", profile.model or "-", str(endpoint)])


def tier_of(requires: Any) -> str:
    """The tier a step's evidence counts at: its required tier, ``basic`` when it names none."""
    return getattr(requires, "tier", None) or "basic"


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _record_path(home: Path) -> Path:
    from .capability_check import record_path

    return record_path(home)


def _lock(home: Path) -> Any:
    from .capability_check import RECORD_LOCK

    return file_lock(Path(home) / RECORD_LOCK)


def load_models(home: Path) -> dict[str, Any]:
    """route key -> its record. Missing file: none. Raises ``AssessmentError`` for an unreadable file."""
    p = _record_path(home)
    if not p.is_file():
        return {}
    try:
        raw = load_yaml(p) or {}
    except YamlError as e:
        raise AssessmentError(f"{p}: {e}") from e
    if not isinstance(raw, dict):
        raise AssessmentError(f"{p}: expected a mapping")
    return {str(k): v for k, v in (raw.get("models") or {}).items() if isinstance(v, dict)}


def _save_models(home: Path, models: dict[str, Any]) -> None:
    from .capability_check import save_section

    save_section(home, "models", dict(sorted(models.items())))


def _fresh(profile_name: str, profile: Any, harness_version: str | None) -> dict[str, Any]:
    return {"model_id": profile.model_id, "adapter": profile.adapter, "provider": profile.provider, "model": profile.model,
            "harness_version": harness_version, "rated": profile.tier, "profiles": [profile_name], "next": 1,
            "totals": {}, "outcomes": [], "owner": {}}


def record_outcome(home: Path, profile_name: str, profile: Any, outcome: dict[str, Any], *, settings: Any,
                   harness_version: str | None = None) -> dict[str, Any] | None:
    """Add one outcome; return ``{tier, before, after}`` when its standing at the tier changed, else ``None``.

    ``outcome``: ``id``, ``kind`` (``trial``, ``shadow``, ``step``), ``tier``, ``passed``, and optionally ``counted``
    (default true), ``capabilities``, ``cost_usd``, ``run``, ``step_path``, ``attempt``, ``reasons``. A repeated id is
    ignored. An alias records nothing.
    """
    key = route_key(profile)
    if key is None:
        return None
    with _lock(home):
        models = load_models(home)
        rec = models.get(key)
        if rec is None or (harness_version and rec.get("harness_version") and rec["harness_version"] != harness_version) \
                or rec.get("rated") != profile.tier:
            rec = _fresh(profile_name, profile, harness_version)  # a new harness or rating starts afresh (0179 item 5, 0182 item 2)
        if harness_version:
            rec["harness_version"] = harness_version
        if profile_name not in rec["profiles"]:
            rec["profiles"] = sorted({*rec["profiles"], profile_name})
        if any(o.get("id") == outcome["id"] for o in rec["outcomes"]):
            return None
        tier = outcome["tier"]
        before = standing(rec, tier, settings, profile.tier)["state"]
        row = {"n": rec["next"], "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "counted": True, **outcome}
        rec["next"] += 1
        rec["outcomes"] = [*rec["outcomes"], row][-KEEP:]
        if row["counted"]:
            t = rec["totals"].setdefault(tier, {}).setdefault(row["kind"], {"passed": 0, "failed": 0})
            t["passed" if row["passed"] else "failed"] += 1
            if row.get("cost_usd") is not None:
                rec["totals"][tier].setdefault("cost_usd", 0.0)
                rec["totals"][tier]["cost_usd"] = round(rec["totals"][tier]["cost_usd"] + float(row["cost_usd"]), 6)
        after = standing(rec, tier, settings, profile.tier)["state"]
        models[key] = rec
        _save_models(home, models)
    return {"tier": tier, "before": before, "after": after} if before != after else None


def standing(rec: dict[str, Any] | None, tier: str, settings: Any, rated: str | None) -> dict[str, Any]:
    """A route's standing at ``tier``: ``state`` (``proven``, ``put_back``, ``candidate``), ``by``, and the counts.

    A record made under another rating than ``rated`` is void (0182, item 2): the route is a candidate again.
    """
    out: dict[str, Any] = {"state": "candidate", "by": "evidence", "passes": 0, "recent_failures": 0, "recent": 0}
    if not rec or rec.get("rated") != rated:
        return out
    owner = (rec.get("owner") or {}).get(tier) or {}
    since = int(owner.get("after", 0))
    rows = [o for o in rec.get("outcomes") or [] if o.get("tier") == tier and o.get("kind") in STANDING_KINDS
            and o.get("counted", True) and int(o.get("n", 0)) > since]
    recent = rows[-settings.window:]
    out.update(passes=sum(1 for o in rows if o.get("passed")), recent_failures=sum(1 for o in recent if not o.get("passed")), recent=len(recent))
    if out["recent_failures"] >= settings.put_back_after:
        out["state"] = "put_back"
        out["failures"] = [{k: o.get(k) for k in ("date", "run", "step_path", "attempt", "kind")} for o in recent if not o.get("passed")]
        return out
    if owner.get("standing") in ("proven", "put_back"):
        out.update(state=owner["standing"], by="owner", date=owner.get("date"))
        return out
    if out["passes"] >= settings.proven_after and out["recent_failures"] == 0 and out["recent"] >= min(settings.window, settings.proven_after):
        out["state"] = "proven"
    return out


def set_standing(home: Path, profile_name: str, profile: Any, tier: str, value: str | None) -> dict[str, Any]:
    """The owner promotes (``proven``), puts back (``put_back``) or clears (``None``) a route's standing at ``tier``."""
    key = route_key(profile)
    if key is None:
        raise AssessmentError(f"{profile_name} has no model identity (an alias, a person or a program): it earns no standing")
    with _lock(home):
        models = load_models(home)
        rec = models.get(key)
        if rec is None or rec.get("rated") != profile.tier:
            rec = _fresh(profile_name, profile, None)
        owner = dict(rec.get("owner") or {})
        if value is None:
            owner.pop(tier, None)
        else:
            owner[tier] = {"standing": value, "date": dt.date.today().isoformat(), "after": rec["next"] - 1}
        rec["owner"] = owner
        models[key] = rec
        _save_models(home, models)
    return {"profile": profile_name, "tier": tier, "standing": value or "evidence"}


def put_back_tiers(models: dict[str, Any], profile: Any, settings: Any, tiers: Iterable[str]) -> list[str]:
    """The tiers at which this route is put back, lowest first."""
    rec = models.get(route_key(profile) or "")
    return [t for t in tiers if standing(rec, t, settings, profile.tier)["state"] == "put_back"]


def summary(models: dict[str, Any], profile: Any, settings: Any, tiers: Iterable[str]) -> dict[str, Any] | None:
    """The route's track record for ``workers status`` and the setup page."""
    key = route_key(profile)
    rec = models.get(key or "")
    if key is None or rec is None:
        return None
    stale = rec.get("rated") != profile.tier
    by_tier = {}
    for t in tiers:
        tot = {} if stale else (rec.get("totals") or {}).get(t) or {}
        st = standing(rec, t, settings, profile.tier)
        if tot or st["state"] != "candidate":
            by_tier[t] = {**{k: v for k, v in tot.items()}, "standing": st["state"], "standing_by": st["by"],
                          **({"failures": st["failures"]} if "failures" in st else {})}
    return {"key": key, "harness_version": rec.get("harness_version"), "by_tier": by_tier}


def machine_profiles(home: Path) -> dict[str, Any]:
    """The machine's generated and owner profiles by name (no project's), for the owner's standing commands."""
    from .profiles import validate_profiles
    from .project import GENERATED_PROFILES, MACHINE_PROFILES
    from .vocab import DEFAULT, load

    vocab = load(DEFAULT)
    out: dict[str, Any] = {}
    gen = Path(home) / GENERATED_PROFILES
    for path in sorted(gen.glob("*.yaml")) if gen.is_dir() else []:
        try:
            found, _ = validate_profiles({path.stem: load_yaml(path)}, vocab, source=str(path))
        except YamlError:  # expected: setup reports an unreadable profile file
            continue
        out.update(found)
    own = Path(home) / MACHINE_PROFILES
    if own.is_file():
        try:
            found, _ = validate_profiles(load_yaml(own) or {}, vocab, source=str(own))
            out.update(found)
        except YamlError:  # expected: reported wherever the profiles are loaded
            pass
    return out


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------


def trial_problems(step: Any, step_path: str, level: dict[str, str] | None = None) -> list[str]:
    """Why ``step`` may not be tried on a candidate; empty when it may (0179, items 1-3)."""
    from .models import ReviewGate, SchemaGate, ScriptGate
    from .packet import gate_included

    out: list[str] = []
    if step.requires is None:
        return ["a program step"]
    if "human_judgment" in step.requires.capabilities:
        out.append("a step for a person")
    if "~" in step_path.rsplit("/", 1)[-1]:
        out.append("a review")
    if tier_of(step.requires) == "strong":
        out.append("it requires a strong model (strong steps are shadowed instead)")
    if step.effect not in ("none", "reversible"):
        out.append(f"its effect is {step.effect or 'not declared'}")
    gates = [g for g in step.gates if not g.advisory and gate_included(g, level or {})]
    if not step.output_schema or not any(isinstance(g, SchemaGate) for g in gates):
        out.append("it has no blocking schema gate")
    if not any(isinstance(g, (ScriptGate, ReviewGate)) for g in gates):
        out.append("it has no blocking script gate or review")
    return out


def price_usd(profile: Any) -> tuple[float, float] | None:
    pr = profile.price or {}
    if pr.get("input") is None or pr.get("output") is None:
        return None
    return float(pr["input"]), float(pr["output"])


def estimate_usd(profile: Any) -> float | None:
    """A conservative cost of one attempt (0179, item 4): 0 for a free or subscription route, ``None`` with no price."""
    from .routing import included

    if included(profile) or (profile.price or {}).get("free"):
        return 0.0
    pr = price_usd(profile)
    if pr is None:
        return None
    ctx = min(profile.context_tokens or ESTIMATE_CONTEXT_TOKENS, ESTIMATE_CONTEXT_TOKENS)
    return round(ctx * ESTIMATE_CALLS * pr[0] / 1e6 + ESTIMATE_OUTPUT_TOKENS * pr[1] / 1e6, 6)


def trial_candidate(step: Any, step_path: str, chosen: str, eligible: list[str], profiles: dict[str, Any], settings: Any,
                    models: dict[str, Any], *, available_usd: float, already_tried: bool,
                    level: dict[str, str] | None = None) -> tuple[str | None, list[str]]:
    """``(candidate, why not)``: the model to try in place of ``chosen``, or ``None`` with the reasons (0179 item 1, 0176 item 6).

    ``eligible`` is routing's eligible set: every tier, capability and independence rule already holds for each.
    """
    from .routing import price_rank

    if not settings.trials:
        return None, ["trials are off"]
    if already_tried:
        return None, ["this step was already tried on a candidate in this run"]
    why = trial_problems(step, step_path, level)
    if why:
        return None, why
    fallback = profiles.get(chosen)
    if fallback is None or fallback.adapter == "manual":
        return None, ["the chosen worker is a person"]
    tier = tier_of(step.requires)
    mine = route_key(fallback)
    options = []
    for name in eligible:
        p = profiles.get(name)
        if name == chosen or p is None or p.adapter in ("manual", "program", "command"):
            continue
        key = route_key(p)
        if key is None or key == mine:
            continue  # an alias earns no standing; the same route is no trial
        if standing(models.get(key), tier, settings, p.tier)["state"] != "candidate":
            continue
        if price_rank(p) >= price_rank(fallback):
            continue  # free or cheaper only (0176, item 6)
        est = estimate_usd(p)
        if est is None or est > available_usd:
            continue  # no price, or more than the day's budget leaves (0179, item 4)
        options.append((price_rank(p), name))
    if not options:
        return None, ["no eligible model is free or cheaper than the chosen worker, unproven at this tier and within the budget"]
    return sorted(options)[0][1], []


# ---------------------------------------------------------------------------
# Shadow attempts (0175 item 3, 0176 items 4 and 6, 0179 items 4-6, 0182 item 1)
# ---------------------------------------------------------------------------


def shadow_problems(step: Any, step_path: str, level: dict[str, str] | None = None) -> list[str]:
    """Why ``step`` may not be shadowed; empty when it may."""
    from .models import SchemaGate
    from .packet import gate_included

    if step.requires is None:
        return ["a program step"]
    out: list[str] = []
    if "human_judgment" in step.requires.capabilities:
        out.append("a step for a person")
    if "~" in step_path.rsplit("/", 1)[-1]:
        out.append("a review")
    if tier_of(step.requires) != "strong":
        out.append("it does not require a strong model (steps below strong are tried instead)")
    if step.workspace == "write":
        out.append("it writes to the workspace")
    if not step.repeatable or step.effect != "none":
        out.append("it does not declare that it can be evaluated again safely (repeatable, effect: none)")
    if not step.output_schema or not any(isinstance(g, SchemaGate) and not g.advisory and gate_included(g, level or {}) for g in step.gates):
        out.append("it has no blocking schema gate to grade a candidate by")
    return out


def shadow_candidate(step: Any, step_path: str, primary: str, eligible: list[str], profiles: dict[str, Any], settings: Any,
                     models: dict[str, Any], *, available_usd: float, already: bool,
                     level: dict[str, str] | None = None) -> tuple[str | None, list[str]]:
    """``(candidate, why not)``: one model to shadow ``primary`` on a strong step (0176, item 6: at most one per step).

    Eligible for the step (so rated strong, with every capability and independence rule), a model identity, not the
    primary's route, not yet proven or put back at strong, within the budget; free first, then the cheapest.
    """
    from .routing import price_rank

    if not settings.shadows:
        return None, ["shadow attempts are off"]
    if already:
        return None, ["this step was already shadowed in this run"]
    why = shadow_problems(step, step_path, level)
    if why:
        return None, why
    mine = route_key(profiles[primary]) if primary in profiles else None
    options = []
    for name in eligible:
        p = profiles.get(name)
        if name == primary or p is None or p.adapter in ("manual", "program", "command"):
            continue
        key = route_key(p)
        if key is None or key == mine:
            continue
        if standing(models.get(key), "strong", settings, p.tier)["state"] != "candidate":
            continue
        est = estimate_usd(p)
        if est is None or est > available_usd:
            continue
        options.append((price_rank(p), name))
    if not options:
        return None, ["no other eligible model is unproven at strong and within the budget"]
    return sorted(options)[0][1], []


def shadow_outcome(shadow: dict[str, Any], primary_failed_gates: bool) -> tuple[bool, bool]:
    """``(passed, counted)`` for a shadow once both it and its primary have ended (0182, item 1).

    Its own gates decide; a failure the primary shared (the primary also failed its schema or script gates) is not
    counted against the candidate; a shadow that could not finish is no evidence. Order cannot change the answer.
    """
    if not shadow.get("counted", True):
        return False, False
    if shadow.get("passed"):
        return True, True
    return False, not primary_failed_gates


# ---------------------------------------------------------------------------
# The budget (0179, item 4)
# ---------------------------------------------------------------------------


def _spend_path(home: Path) -> Path:
    return Path(home) / SPEND_FILE


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _load_spend(home: Path) -> dict[str, Any]:
    p = _spend_path(home)
    if not p.is_file():
        return {"date": _today(), "reservations": {}}
    try:
        raw = load_yaml(p) or {}
    except YamlError as e:
        raise AssessmentError(f"{p}: {e}") from e
    if not isinstance(raw, dict) or raw.get("date") != _today():
        return {"date": _today(), "reservations": {}}  # a new day starts empty
    return {"date": raw["date"], "reservations": dict(raw.get("reservations") or {})}


def _save_spend(home: Path, body: dict[str, Any]) -> None:
    from .resources import _atomic_write

    header = "# What trials and shadow attempts reserved and spent today (§6.4, Decision 0179 item 4). Written by Baton.\n"
    _atomic_write(_spend_path(home), header + yaml.safe_dump(body, sort_keys=False))


def spent(body: dict[str, Any]) -> float:
    total = 0.0
    for r in body["reservations"].values():
        v = r.get("actual_usd") if r.get("actual_usd") is not None else r.get("estimate_usd", 0.0)
        total += float(v or 0.0)
    return round(total, 6)


def available(home: Path, settings: Any) -> float:
    return max(0.0, round(settings.daily_limit_usd - spent(_load_spend(home)), 6))


def reserve(home: Path, rid: str, estimate: float, settings: Any, **about: Any) -> bool:
    """Claim ``estimate`` against today's limit under the machine-wide lock; ``False`` when it does not fit."""
    with file_lock(Path(home) / SPEND_LOCK):
        body = _load_spend(home)
        if rid in body["reservations"]:
            return True
        if estimate > 0 and spent(body) + estimate > settings.daily_limit_usd + 1e-9:
            return False
        body["reservations"][rid] = {"estimate_usd": estimate, **about}
        _save_spend(home, body)
    return True


def reconcile(home: Path, rid: str, actual: float | None) -> None:
    """Replace a reservation's estimate with what the attempt cost; unknown keeps the estimate."""
    with file_lock(Path(home) / SPEND_LOCK):
        body = _load_spend(home)
        r = body["reservations"].get(rid)
        if r is None or r.get("reconciled"):
            return
        r["reconciled"] = True
        if actual is not None:
            r["actual_usd"] = round(float(actual), 6)
        _save_spend(home, body)


def release(home: Path, rid: str) -> None:
    """Drop a reservation for a dispatch that never started."""
    with file_lock(Path(home) / SPEND_LOCK):
        body = _load_spend(home)
        if body["reservations"].pop(rid, None) is not None:
            _save_spend(home, body)


def budget_status(home: Path, settings: Any) -> dict[str, Any]:
    try:
        body = _load_spend(home)
    except AssessmentError:
        body = {"date": _today(), "reservations": {}}
    return {"date": body["date"], "limit_usd": settings.daily_limit_usd, "reserved_or_spent_usd": spent(body),
            "available_usd": max(0.0, round(settings.daily_limit_usd - spent(body), 6)), "dispatches": len(body["reservations"])}


def usage_cost(attempt_dir: Path) -> float | None:
    """The cost the runner measured for an attempt (``usage.json``, Decision 0177), or ``None``."""
    try:
        u = json.loads((Path(attempt_dir) / "usage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # expected: a route that measures nothing (a harness CLI) writes no usage record
        return None
    c = u.get("cost_usd") if isinstance(u, dict) else None
    return float(c) if isinstance(c, (int, float)) else None
