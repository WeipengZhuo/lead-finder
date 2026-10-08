#!/usr/bin/env python3
"""lf.py -- the Lead Finder engine.

Everything deterministic lives here: treg calls, spend caps, cache, ledger,
privacy scrubbing, dedupe, exclusions, the verification rule and export.
Claude does the judgment (interview, queries, screening, picking contacts,
openers). This script never sends email and never touches a messaging API.

Single file, standard library only, Python 3.9 or newer.
Contract: docs/contracts.md in the internal repo (sections 3 to 10).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SELF = Path(__file__).resolve()


def _plugin_version() -> str:
    """The version in the plugin's own plugin.json, so the engine never reports a stale one."""
    try:
        meta = json.loads((SELF.parent.parent / ".claude-plugin" / "plugin.json").read_text())
        return str(meta.get("version") or "dev")
    except (OSError, ValueError, AttributeError):
        return "dev"


VERSION = _plugin_version()

DEFAULT_BASE_URL = "https://treg.to"
TRANSPORTS = ("http", "cli", "ingest")
STAGES = ("search", "fetch", "contacts", "emails", "verify", "other")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_TRANSPORT = 3
EXIT_BUDGET = 4
EXIT_BALANCE = 5
EXIT_INGEST = 6
EXIT_CAP = 7

HARD_MAX_COST = 0.05
DEFAULT_MAX_COST = 0.01
SEARCH_PER_MINUTE = 25
HTTP_TIMEOUT = 60
CLI_TIMEOUT = 120
HITS_PRINT_LIMIT = 200

# endpoint -> method, expected price (USD, used for budget estimates), default
# per-call max-cost header (USD).
ENDPOINTS: dict[str, dict[str, Any]] = {
    "tinyfish.web.search": {"method": "GET", "price": 0.0, "max_cost": 0.01},
    "tinyfish.web.fetch": {"method": "POST", "price": 0.0, "max_cost": 0.01},
    "treg.companies.search": {"method": "POST", "price": 0.002, "max_cost": 0.01},
    "treg.people.search": {"method": "POST", "price": 0.0025, "max_cost": 0.01},
    "getleadsio.people.decision_makers": {"method": "POST", "price": 0.0, "max_cost": 0.01},
    "treg.people.email.find": {"method": "POST", "price": 0.01, "max_cost": 0.01},
    "treg.people.email.verify": {"method": "POST", "price": 0.002, "max_cost": 0.005},
    "bounceban.people.email.verify": {"method": "GET", "price": 0.004, "max_cost": 0.01},
    "exa.web.search": {"method": "POST", "price": 0.007, "max_cost": 0.01},
    "tinyfish.web.search.news": {"method": "GET", "price": 0.0, "max_cost": 0.01},
    "anyapi.linkedin.search.posts": {"method": "POST", "price": 0.002, "max_cost": 0.01},
}

EP_SEARCH = "tinyfish.web.search"
EP_FETCH = "tinyfish.web.fetch"
EP_PEOPLE = "treg.people.search"
# Header that makes the people.search router skip providers that ignore the title filter.
# It changes the answer, so it is part of the cache key.
STRICT_HEADERS = {"X-Treg-Route-Strict-Filters": "1"}
EP_FIND = "treg.people.email.find"
EP_VERIFY = "treg.people.email.verify"
EP_BOUNCEBAN = "bounceban.people.email.verify"

CAND_FIELDS = [
    "org", "domain", "org_type", "event", "event_date", "event_url", "cfp_deadline",
    "why_fit", "source_urls", "contact_name", "contact_title", "contact_source",
    "linkedin", "email", "email_source", "find_verified", "find_served_by",
    "email_check", "verify_detail", "status", "status_reason", "opener",
]
STATUSES = ("new", "excluded", "ready", "verified", "risky", "dead")
ADD_STATUSES = ("new", "excluded", "ready")  # verified / risky / dead are set by `verify` only
SET_STATUSES = ("new", "excluded", "ready", "dead")

LEADS_COLUMNS = [
    "#", "Organization", "Event", "Event date", "Event / speaker page",
    "Speaker call deadline", "Contact", "Title", "Email", "Email check",
    "LinkedIn", "Why it fits", "Draft opener (edit freely)",
]

INTERMEDIARY_KEYWORDS = [
    "speakers bureau", "speaker bureau", "talent agency", "booking agency",
    "event production", "events by", "productions", "meeting planning",
    "staffing", "recruiting",
]

# Free-mail: a registered label that matches in any TLD, plus a few exact hosts.
FREEMAIL_LABELS = {
    "gmail", "yahoo", "hotmail", "outlook", "aol", "icloud", "msn", "live",
    "proton", "protonmail", "gmx", "ymail",
}
FREEMAIL_HOSTS = {"me.com", "mail.com", "comcast.net"}

ACCEPT_ALL_STATUSES = {"accept_all", "catch_all", "catchall", "unknown", "risky"}
VALID_STATUSES = {"valid", "deliverable"}
INVALID_STATUSES = {"invalid", "undeliverable"}
BOUNCEBAN_MIN_SCORE = 97
# Endpoints whose result carries its own charged_micro; ingest trusts it over an estimate.
CHARGE_IN_RESULT = {"treg.people.email.find"}
# What calls usually cost (measured 2026-10-04, see references/endpoints.md). `estimate` uses these
# so a default brief quotes a realistic number; the per-run guard keeps using the ENDPOINTS
# prices above, which are the worst usual case.
TYPICAL_PRICES = {
    "tinyfish.web.search": 0.0,
    "treg.people.search": 0.0025,
    "treg.people.email.find": 0.005,
    "treg.people.email.verify": 0.0,
    "bounceban.people.email.verify": 0.004,
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
EMAIL_FULL_RE = re.compile(r"^\s*[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+\s*$")
DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)+$")
SLUG_ARG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._\-]*$")
BRIEF_SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[a-z0-9]+(?:-[a-z0-9]+)*$")
# Built from two pieces so the source never contains a literal token prefix.
TOKEN_RE = re.compile("tr" + "eg_[A-Za-z0-9_\\-]{8,}")

_SECRETS: set[str] = set()


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------


class LfError(Exception):
    """Base class for expected failures."""


class UsageError(LfError):
    """Bad input from the user or from Claude. Exit 2."""


class TransportUnavailable(LfError):
    """No usable transport (no token, no CLI, no route). Exit 3."""


class TransportError(LfError):
    """A single call failed at the network or process level."""


class BudgetReached(LfError):
    def __init__(
        self, spent_micro: int, budget_micro: int, next_micro: int = 0, pending_micro: int = 0
    ) -> None:
        super().__init__("budget reached")
        self.spent_micro = spent_micro  # actual ledger spend, never includes queued calls
        self.budget_micro = budget_micro
        self.next_micro = next_micro
        self.pending_micro = pending_micro


class OutOfBalance(LfError):
    """A 402 that is not a per-call price cap. Exit 5."""


class CallCapReached(LfError):
    """A treg account-level limit (the token's daily call cap, or a team/tag cap). Exit 7."""


class NeedsIngest(LfError):
    def __init__(self, req: dict[str, Any]) -> None:
        super().__init__("needs ingest")
        self.req = req


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def redact(text: Any) -> str:
    """Remove the token (and anything token-shaped) from a string."""
    s = str(text)
    for secret in _SECRETS:
        if secret:
            s = s.replace(secret, "[redacted]")
    return TOKEN_RE.sub("[redacted]", s)


def eprint(msg: str) -> None:
    print(redact(msg), file=sys.stderr)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def usd_to_micro(usd: float) -> int:
    return int(round(float(usd) * 1_000_000))


def fmt_usd(micro: int) -> str:
    return "$%.4f" % (micro / 1_000_000)


def fmt_cap(usd: float) -> str:
    text = ("%.6f" % usd).rstrip("0").rstrip(".")
    return text or "0"


def write_text(path: Path, text: str, mode: int | None = None, scrub: bool = True) -> None:
    """Atomic write. Redacts known secrets before anything reaches disk (config.json opts out)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = redact(text) if scrub else text
    if mode is None:
        tmp.write_text(data, encoding="utf-8")
    else:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.chmod(str(tmp), mode)
    os.replace(str(tmp), str(path))


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(redact(text))


def norm_domain(value: Any) -> str:
    v = str(value or "").strip().lower()
    v = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", v)
    v = re.split(r"[/?#]", v, maxsplit=1)[0]
    v = v.split("@")[-1].split(":")[0]
    if v.startswith("www."):
        v = v[4:]
    return v.strip(".")


def host_of(url: str) -> str:
    try:
        return norm_domain(urllib.parse.urlparse(url).netloc or url)
    except ValueError:
        return ""


def same_domain(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def is_freemail_domain(host: str) -> bool:
    host = host.strip().lower().strip(".")
    if not host:
        return False
    for h in FREEMAIL_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    parts = host.split(".")
    if len(parts) >= 2 and parts[-2] in FREEMAIL_LABELS:
        return True
    if len(parts) >= 3 and parts[-2] in ("co", "com") and parts[-3] in FREEMAIL_LABELS:
        return True
    return False


def is_freemail(email: str) -> bool:
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    return is_freemail_domain(email.rsplit("@", 1)[1])


# --------------------------------------------------------------------------
# sanitize (contract section 8)
# --------------------------------------------------------------------------

_TEL_KEY_RE = re.compile(r"(?:^|[^a-z])tel(?:[^a-z]|$)")
_BLOCKED_KEY_PARTS = ("phone", "mobile", "personal_email", "home_address", "address_line")


def _blocked_key(key: str) -> bool:
    k = key.lower()
    if any(part in k for part in _BLOCKED_KEY_PARTS):
        return True
    return bool(_TEL_KEY_RE.search(k))


def _scrub_str(value: str) -> str | None:
    """Return None when the whole string is a free-mail address."""
    if EMAIL_FULL_RE.match(value) and is_freemail(value):
        return None

    def repl(m: re.Match[str]) -> str:
        return "[removed]" if is_freemail(m.group(0)) else m.group(0)

    return EMAIL_RE.sub(repl, value)


def sanitize(obj: Any) -> Any:
    """Recursively drop phone-like keys and free-mail addresses. Pure."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if _blocked_key(str(key)):
                continue
            if isinstance(val, str):
                scrubbed = _scrub_str(val)
                if scrubbed is None:
                    continue
                out[key] = scrubbed
            else:
                out[key] = sanitize(val)
        return out
    if isinstance(obj, list):
        items: list[Any] = []
        for val in obj:
            if isinstance(val, str):
                scrubbed = _scrub_str(val)
                if scrubbed is None:
                    continue
                items.append(scrubbed)
            else:
                items.append(sanitize(val))
        return items
    return obj


# --------------------------------------------------------------------------
# context
# --------------------------------------------------------------------------


class Ctx:
    def __init__(
        self,
        home: Path,
        transport: str | None = None,
        fresh: bool = False,
        as_json: bool = False,
        max_cost: float | None = None,
        allow_expensive: bool = False,
        token: str = "",
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.home = home
        self.transport = transport
        self.fresh = fresh
        self.as_json = as_json
        self.max_cost = max_cost
        self.allow_expensive = allow_expensive
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.run: str | None = None
        self.recipe: str | None = None
        self.budget_usd: float | None = None
        self.pending: list[dict[str, Any]] = []
        self.pending_micro = 0
        self.lines: list[str] = []
        self.notes: list[str] = []
        self.data: dict[str, Any] = {}
        self.ok_calls = 0
        self.transport_errors = 0
        self._search_times: deque[float] = deque()
        if token:
            _SECRETS.add(token)

    def say(self, line: str = "") -> None:
        self.lines.append(line)

    @property
    def run_dir(self) -> Path:
        if not self.run:
            raise UsageError("no run selected")
        return self.home / "runs" / self.run

    def throttle(self, endpoint: str) -> None:
        if endpoint != EP_SEARCH:
            return
        now = _now()
        while self._search_times and now - self._search_times[0] >= 60:
            self._search_times.popleft()
        if len(self._search_times) >= SEARCH_PER_MINUTE:
            wait = 60 - (now - self._search_times[0]) + 0.05
            _sleep(max(wait, 0.0))
            now = _now()
            while self._search_times and now - self._search_times[0] >= 60:
                self._search_times.popleft()
        self._search_times.append(_now())


CTX: Ctx | None = None


def set_ctx(ctx: Ctx | None) -> None:
    global CTX
    CTX = ctx


def find_treg() -> str | None:
    env_bin = os.environ.get("TREG_BIN")
    if env_bin:
        return env_bin if (os.path.exists(env_bin) or shutil.which(env_bin)) else None
    return shutil.which("treg")


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def load_config(home: Path) -> dict[str, Any]:
    p = home / "config.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_transport(arg: str | None, cfg: dict[str, Any]) -> str:
    choice = arg or cfg.get("transport")
    if choice in TRANSPORTS:
        return str(choice)
    if cfg.get("token"):
        return "http"
    if find_treg():
        return "cli"
    return "ingest"


# --------------------------------------------------------------------------
# cache and ledger (contract section 6)
# --------------------------------------------------------------------------


def endpoint_method(endpoint: str, body: Any = None) -> str:
    info = ENDPOINTS.get(endpoint)
    if info:
        return str(info["method"])
    return "POST" if body is not None else "GET"


def expected_micro(endpoint: str) -> int:
    info = ENDPOINTS.get(endpoint)
    price = info["price"] if info else DEFAULT_MAX_COST
    return usd_to_micro(price)


def cache_key(
    endpoint: str, method: str, params: Any, body: Any, headers: dict[str, str] | None = None
) -> str:
    """`headers` holds only request headers that change the answer (strict filters).

    Without them the key material is unchanged, so existing caches stay valid.
    """
    parts = [endpoint, method, canonical_json(params), canonical_json(body)]
    if headers:
        parts.append(canonical_json(headers))
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(home: Path, key: str) -> Path:
    return home / "cache" / (key + ".json")


def cache_read(home: Path, key: str) -> dict[str, Any] | None:
    try:
        data = json.loads(cache_path(home, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and "result" in data and isinstance(data.get("_treg"), dict):
        return data
    return None


def cache_write(home: Path, key: str, env: dict[str, Any]) -> None:
    write_text(cache_path(home, key), json.dumps(env, ensure_ascii=False))


def ledger_path(home: Path) -> Path:
    return home / "ledger.jsonl"


def read_ledger(home: Path) -> list[dict[str, Any]]:
    try:
        text = ledger_path(home).read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def ledger_append(
    ctx: Ctx, stage: str, endpoint: str, method: str, meta: dict[str, Any], cache_hit: bool
) -> None:
    row = {
        "ts": now_iso(),
        "run": ctx.run or "-",
        "stage": stage if stage in STAGES else "other",
        "endpoint": endpoint,
        "method": method,
        "http_status": to_int(meta.get("http_status"), 0),
        "call_id": str(meta.get("call_id") or ""),
        "charged_micro": 0 if cache_hit else to_int(meta.get("charged_micro"), 0),
        "served_by": str(meta.get("served_by") or ""),
        "cache_hit": bool(cache_hit),
    }
    append_text(ledger_path(ctx.home), json.dumps(row, ensure_ascii=False) + "\n")


def run_spent_micro(home: Path, run: str) -> int:
    return sum(to_int(r.get("charged_micro"), 0) for r in read_ledger(home) if r.get("run") == run)


# --------------------------------------------------------------------------
# transports (contract section 5)
# --------------------------------------------------------------------------


def meta_value(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:\-]", "-", str(value or ""))[:128]
    return cleaned or "-"


def meta_header(ctx: Ctx) -> str:
    return "run=%s,recipe=%s" % (meta_value(ctx.run), meta_value(ctx.recipe))


def resolve_max_cost(ctx: Ctx, endpoint: str, override: float | None) -> float:
    info = ENDPOINTS.get(endpoint)
    value = DEFAULT_MAX_COST if not info else float(info["max_cost"])
    if override is not None:
        value = float(override)
    elif ctx.max_cost is not None:
        value = float(ctx.max_cost)
    if value < 0:
        raise UsageError("max cost cannot be negative")
    if not ctx.allow_expensive and value > HARD_MAX_COST:
        value = HARD_MAX_COST
    return value


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (params or {}).items():
        if v is None:
            continue
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            out[k] = [str(x) for x in v]
        else:
            out[k] = str(v)
    return out


def make_env(
    result: Any, http_status: int, call_id: str = "", charged_micro: int = 0,
    served_by: str = "", cache_hit: bool = False,
) -> dict[str, Any]:
    return {
        "result": result,
        "_treg": {
            "http_status": int(http_status),
            "call_id": str(call_id or ""),
            "charged_micro": int(charged_micro),
            "served_by": str(served_by or ""),
            "cache_hit": bool(cache_hit),
        },
    }


def normalize_env(
    data: Any, cost_micro: int | None = None, default_micro: int | None = None
) -> dict[str, Any]:
    """Turn a treg CLI line, a saved MCP result or a bare provider body into an Envelope."""
    if isinstance(data, dict) and "result" in data and isinstance(data.get("_treg"), dict):
        result = data["result"]
        meta = data["_treg"]
    else:
        result = data
        meta = {}
    inner = result.get("_treg") if isinstance(result, dict) else None
    inner = inner if isinstance(inner, dict) else {}
    served_by = meta.get("served_by") or inner.get("served_by") or ""
    charged = meta.get("charged_micro")
    if charged is None:
        charged = inner.get("charged_micro")
    status = to_int(meta.get("http_status"), 200)
    if cost_micro is not None:
        charged = cost_micro
    elif charged is None and default_micro is not None and 200 <= status < 300:
        charged = default_micro
    return make_env(
        result,
        status,
        str(meta.get("call_id") or ""),
        to_int(charged, 0),
        str(served_by),
        False,
    )


def _parse_body(text: str) -> Any:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        return {"error": text[:500]}


def _send_http(ctx: Ctx, req: dict[str, Any]) -> dict[str, Any]:
    if not ctx.token:
        raise TransportUnavailable(
            "No treg token is configured. Run the setup command, then try again."
        )
    method = req["method"]
    url = "%s/call/%s" % (ctx.base_url, req["endpoint"])
    params = _clean_params(req.get("params"))
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    headers = {
        "X-Treg-Token": ctx.token,
        "X-Treg-Route-Max-Cost": fmt_cap(req["max_cost"]),
        "X-Treg-Meta": req["meta"],
        "Accept": "application/json",
        "User-Agent": "lead-finder/%s" % VERSION,
    }
    headers.update(req.get("headers") or {})
    data = None
    if method != "GET":
        headers["Content-Type"] = "application/json"
        data = json.dumps(req.get("body") if req.get("body") is not None else {}).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(request, timeout=HTTP_TIMEOUT, context=ssl_context())
        status = resp.getcode()
    except urllib.error.HTTPError as exc:
        resp = exc
        status = exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TransportError("network error: %s" % redact(exc))
    try:
        raw = resp.read().decode("utf-8", errors="replace")
        hdr = resp.headers
        micro = to_int(hdr.get("X-Treg-Cost-Micro"), 0)
        call_id = hdr.get("X-Treg-Call-Id") or ""
        served_by = hdr.get("X-Treg-Served-By") or ""
    finally:
        try:
            resp.close()
        except OSError:
            pass
    return make_env(_parse_body(raw), status, call_id, micro, served_by)


def _send_cli(ctx: Ctx, req: dict[str, Any]) -> dict[str, Any]:
    binary = find_treg()
    if not binary:
        raise TransportUnavailable(
            "The treg CLI was not found. Install it, or use the http or ingest transport."
        )
    cmd = [binary, "--json", "call", req["endpoint"]]
    if req["method"] != "GET":
        body = req.get("body") if req.get("body") is not None else {}
        cmd += ["--data", json.dumps(body)]
    for key, val in _clean_params(req.get("params")).items():
        values = val if isinstance(val, list) else [val]
        for item in values:
            cmd += ["--query", "%s=%s" % (key, item)]
    cmd += ["--header", "X-Treg-Route-Max-Cost: %s" % fmt_cap(req["max_cost"])]
    cmd += ["--header", "X-Treg-Meta: %s" % req["meta"]]
    for hname, hval in (req.get("headers") or {}).items():
        cmd += ["--header", "%s: %s" % (hname, hval)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT, check=False
        )
    except FileNotFoundError:
        raise TransportUnavailable("The treg CLI was not found.")
    except subprocess.TimeoutExpired:
        raise TransportError("treg CLI timed out")
    except OSError as exc:
        raise TransportError("treg CLI failed to start: %s" % redact(exc))
    out = (proc.stdout or "").strip()
    parsed: Any = None
    if out:
        try:
            parsed = json.loads(out)
        except ValueError:
            for line in reversed(out.splitlines()):
                try:
                    parsed = json.loads(line)
                    break
                except ValueError:
                    continue
    if not isinstance(parsed, dict):
        raise TransportError(
            "treg CLI exited %d without a JSON result: %s"
            % (proc.returncode, redact((proc.stderr or "").strip()[:200]))
        )
    return normalize_env(parsed)


# CA bundles to fall back on when Python ships without trusted roots (the python.org
# macOS build reports zero CAs until "Install Certificates" is run).
CA_BUNDLE_FALLBACKS = (
    "/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/opt/homebrew/etc/openssl@3/cert.pem",
    "/usr/local/etc/openssl@3/cert.pem",
)
_SSL_CONTEXT: ssl.SSLContext | None = None


def ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        ctx = ssl.create_default_context()
        if not ctx.cert_store_stats().get("x509_ca"):
            for path in CA_BUNDLE_FALLBACKS:
                if os.path.isfile(path):
                    try:
                        ctx.load_verify_locations(cafile=path)
                        break
                    except (OSError, ssl.SSLError):
                        continue
        _SSL_CONTEXT = ctx
    return _SSL_CONTEXT


def transport_send(ctx: Ctx, req: dict[str, Any]) -> dict[str, Any]:
    """The only function that touches the network or a subprocess."""
    if ctx.transport == "cli":
        return _send_cli(ctx, req)
    return _send_http(ctx, req)


def _is_route_cap_402(env: dict[str, Any]) -> bool:
    try:
        text = json.dumps(env.get("result"))
    except (TypeError, ValueError):
        return False
    return "route_max_cost" in text.lower()


# treg refusals that stop every further call today, so a run must stop instead of
# treating each row as a provider miss. The token's own cap is `daily_cap_reached`.
ACCOUNT_CAP_ERRORS = ("daily_cap_reached", "platform_daily_cap_reached",
                      "tag_call_cap_reached", "tag_spend_cap_reached")


def _is_account_cap_429(env: dict[str, Any]) -> bool:
    try:
        text = json.dumps(env.get("result")).lower()
    except (TypeError, ValueError):
        return False
    return any(code in text for code in ACCOUNT_CAP_ERRORS)


def call(
    endpoint: str,
    *,
    method: str | None = None,
    params: dict[str, Any] | None = None,
    body: Any = None,
    stage: str = "other",
    max_cost_usd: float | None = None,
    headers: dict[str, str] | None = None,
    ctx: Ctx | None = None,
) -> dict[str, Any]:
    """ONE function for every treg call: cache, budget, send, sanitize, ledger.

    `headers` are extra request headers that change the answer (see STRICT_HEADERS).
    """
    ctx = ctx or CTX
    if ctx is None:
        raise RuntimeError("no context")
    meth = (method or endpoint_method(endpoint, body)).upper()
    key = cache_key(endpoint, meth, params or {}, body, headers)

    if not ctx.fresh:
        hit = cache_read(ctx.home, key)
        if hit is not None:
            env = json.loads(json.dumps(hit))
            env["_treg"]["cache_hit"] = True
            env["_treg"]["charged_micro"] = 0
            ledger_append(ctx, stage, endpoint, meth, env["_treg"], True)
            ctx.ok_calls += 1
            return env

    price = expected_micro(endpoint)
    if ctx.run and ctx.budget_usd is not None:
        spent = run_spent_micro(ctx.home, ctx.run)
        budget = usd_to_micro(ctx.budget_usd)
        queued = ctx.pending_micro if ctx.transport == "ingest" else 0
        if spent + queued + price > budget:
            raise BudgetReached(spent, budget, price, queued)

    cap = resolve_max_cost(ctx, endpoint, max_cost_usd)
    req = {
        "endpoint": endpoint,
        "method": meth,
        "params": params or {},
        "body": body,
        "stage": stage,
        "max_cost": cap,
        "meta": meta_header(ctx),
        "headers": dict(headers or {}),
    }
    if ctx.transport == "ingest":
        if all(p.get("key") != key for p in ctx.pending):
            ctx.pending_micro += price
        raise NeedsIngest(req)

    ctx.throttle(endpoint)
    env = transport_send(ctx, req)
    env = sanitize(env)
    status = to_int(env["_treg"].get("http_status"), 0)
    ledger_append(ctx, stage, endpoint, meth, env["_treg"], False)
    ctx.ok_calls += 1
    if status == 402 and not _is_route_cap_402(env):
        raise OutOfBalance("out of balance")
    if status == 429 and _is_account_cap_429(env):
        raise CallCapReached("account call limit reached")
    if 200 <= status < 300:
        cache_write(ctx.home, key, env)
    return env


def safe_call(ctx: Ctx, endpoint: str, **kwargs: Any) -> tuple[dict[str, Any] | None, str]:
    """Stage helper. Returns (envelope, "") or (None, "ingest" | "network")."""
    try:
        return call(endpoint, ctx=ctx, **kwargs), ""
    except NeedsIngest as exc:
        key = cache_key(exc.req["endpoint"], exc.req["method"], exc.req["params"], exc.req["body"],
                        exc.req.get("headers"))
        if all(p.get("key") != key for p in ctx.pending):
            ctx.pending.append(dict(exc.req, key=key))
        return None, "ingest"
    except TransportError as exc:
        ctx.transport_errors += 1
        ctx.notes.append("transport error: %s" % redact(exc))
        return None, "network"


def env_ok(env: dict[str, Any] | None) -> bool:
    return env is not None and 200 <= to_int(env["_treg"].get("http_status"), 0) < 300


def env_status(env: dict[str, Any] | None) -> int:
    return to_int(env["_treg"].get("http_status"), 0) if env else 0


def result_of(env: dict[str, Any] | None) -> dict[str, Any]:
    res = env.get("result") if env else None
    return res if isinstance(res, dict) else {}


def output_of(env: dict[str, Any] | None) -> dict[str, Any]:
    res = result_of(env)
    out = res.get("output")
    return out if isinstance(out, dict) else res


# --------------------------------------------------------------------------
# run folder, brief, candidates
# --------------------------------------------------------------------------


def check_slug_arg(slug: str, allow_dash: bool = False) -> str:
    if allow_dash and slug == "-":
        return slug
    if not SLUG_ARG_RE.match(slug or "") or ".." in slug:
        raise UsageError("invalid run slug %r" % slug)
    return slug


def ensure_home(home: Path) -> None:
    (home / "cache").mkdir(parents=True, exist_ok=True)
    (home / "runs").mkdir(parents=True, exist_ok=True)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_brief(data: Any, folder_slug: str | None = None) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["brief.json must be a JSON object"]
    slug = data.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        problems.append("slug is required (a string like 2026-10-05_philly-speaking)")
    else:
        if not BRIEF_SLUG_RE.match(slug):
            problems.append("slug %r should look like YYYY-MM-DD_kebab-name" % slug)
        if folder_slug and slug != folder_slug:
            problems.append("slug %r does not match the run folder %r" % (slug, folder_slug))
    recipe = data.get("recipe")
    if not isinstance(recipe, str) or not recipe.strip():
        problems.append("recipe is required (a non-empty string)")
    tc = data.get("target_count")
    if not isinstance(tc, int) or isinstance(tc, bool) or not 1 <= tc <= 100:
        problems.append("target_count is required and must be an integer from 1 to 100")
    bud = data.get("budget_usd")
    if not _is_num(bud) or not (0 < bud <= 20):
        problems.append("budget_usd is required and must be a number above 0 and at most 20")
    queries = data.get("queries")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 80:
        problems.append("queries is required and must be a list of 1 to 80 items")
    else:
        for i, q in enumerate(queries):
            if not isinstance(q, dict) or not isinstance(q.get("q"), str) or not q["q"].strip():
                problems.append("queries[%d] needs a non-empty \"q\" string" % i)
                continue
            for opt in ("location", "after_date"):
                if opt in q and q[opt] is not None and not isinstance(q[opt], str):
                    problems.append("queries[%d].%s must be a string" % (i, opt))
    for key in ("geo", "org_types", "titles_tier_a", "titles_fallback", "signals"):
        val = data.get(key)
        if val is not None and (
            not isinstance(val, list) or not all(isinstance(x, str) for x in val)
        ):
            problems.append("%s must be a list of strings" % key)
    for key in ("size_min", "size_max"):
        val = data.get(key)
        if val is not None and (not isinstance(val, int) or isinstance(val, bool) or val < 0):
            problems.append("%s must be a non-negative integer" % key)
    smin, smax = data.get("size_min"), data.get("size_max")
    if isinstance(smin, int) and isinstance(smax, int) and smin > smax:
        problems.append("size_min is larger than size_max")
    if data.get("virtual_ok") is not None and not isinstance(data.get("virtual_ok"), bool):
        problems.append("virtual_ok must be true or false")
    for key in ("goal", "offer"):
        if data.get(key) is not None and not isinstance(data.get(key), str):
            problems.append("%s must be a string" % key)
    return problems


def load_brief(ctx: Ctx, slug: str, required: bool = True) -> dict[str, Any] | None:
    check_slug_arg(slug)
    ctx.run = slug
    path = ctx.run_dir / "brief.json"
    if not path.exists():
        if required:
            raise UsageError(
                "runs/%s/brief.json is missing. Write the brief, then run brief-check." % slug
            )
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError("brief.json is not valid JSON: %s" % exc)
    problems = check_brief(data, slug)
    if problems:
        raise UsageError(
            "brief.json has %d problem(s); run brief-check to see them" % len(problems)
        )
    ctx.recipe = str(data["recipe"])
    ctx.budget_usd = float(data["budget_usd"])
    return data


def new_row(domain: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {k: "" for k in CAND_FIELDS}
    row["domain"] = domain
    row["source_urls"] = []
    row["find_verified"] = None
    row["verify_detail"] = {}
    row["status"] = "new"
    return row


def coerce_field(key: str, value: Any) -> Any:
    if key == "source_urls":
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        if isinstance(value, (list, tuple)):
            return [str(s) for s in value]
        return [str(value)]
    if key == "find_verified":
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise UsageError("find_verified must be true, false or empty")
    if key == "verify_detail":
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                raise UsageError("verify_detail must be a JSON object")
            if isinstance(parsed, dict):
                return parsed
        raise UsageError("verify_detail must be a JSON object")
    if value is None:
        return ""
    return str(value).strip()


def refresh_status(row: dict[str, Any]) -> None:
    if row.get("status") in ("new", "ready"):
        row["status"] = "ready" if row.get("contact_name") and row.get("domain") else "new"


def apply_email_rules(row: dict[str, Any]) -> None:
    email = str(row.get("email") or "").strip().lower()
    if email and is_freemail(email):
        row["email"] = ""
        row["status"] = "excluded"
        row["status_reason"] = "free-mail email"
    else:
        row["email"] = email


def load_candidates(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "candidates.jsonl"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            raise UsageError("candidates.jsonl line %d is not valid JSON" % (i + 1))
        if isinstance(obj, dict):
            base = new_row()
            base.update(obj)
            rows.append(base)
    return rows


def save_candidates(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(sanitize(r), ensure_ascii=False) + "\n" for r in rows)
    write_text(run_dir / "candidates.jsonl", text)


def need_rows(ctx: Ctx, slug: str, brief_required: bool = True) -> list[dict[str, Any]]:
    load_brief(ctx, slug, required=brief_required)
    return load_candidates(ctx.run_dir)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except OSError:
        return []


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def add_pending_output(ctx: Ctx) -> None:
    if not ctx.pending:
        return
    items: list[dict[str, Any]] = []
    lines = [
        "NEEDS INGEST: %d treg call(s) must be made with the treg MCP `call` tool "
        "(this script has no network in ingest mode)." % len(ctx.pending),
        "For each: make the call, save its JSON result to a file, run the ingest command, "
        "then re-run the stage command. Cached results are free.",
    ]
    for i, req in enumerate(ctx.pending, 1):
        parts = [
            "python3", shlex.quote(str(SELF)), "--home", shlex.quote(str(ctx.home)),
            "ingest", shlex.quote(ctx.run or "-"), "--stage", req["stage"],
            "--endpoint", req["endpoint"],
        ]
        if req["params"]:
            parts += ["--params", shlex.quote(canonical_json(req["params"]))]
        if req["body"] is not None:
            parts += ["--body", shlex.quote(canonical_json(req["body"]))]
        if req.get("headers"):
            parts += ["--strict"]
        parts += ["--file", "<saved-result.json>"]
        price = ENDPOINTS.get(req["endpoint"], {}).get("price", 0.0)
        if price and req["endpoint"] not in CHARGE_IN_RESULT:
            parts += ["--cost-usd", fmt_cap(price)]
        cmd = " ".join(parts)
        args = req["body"] if req["body"] is not None else req["params"]
        lines += [
            "%d. endpoint: %s" % (i, req["endpoint"]),
            "   method: %s" % req["method"],
            "   arguments: %s" % canonical_json(args),
            "   max cost: %s" % fmt_cap(req["max_cost"]),
        ]
        for hname, hval in (req.get("headers") or {}).items():
            lines.append("   header: %s: %s (pass it if the connector allows headers; "
                         "keep --strict in the ingest command either way)" % (hname, hval))
        lines.append("   then run: %s" % cmd)
        items.append({
            "endpoint": req["endpoint"], "method": req["method"], "params": req["params"],
            "body": req["body"], "stage": req["stage"], "max_cost": req["max_cost"],
            "headers": req.get("headers") or {}, "ingest_command": cmd,
        })
    ctx.lines.extend(lines)
    ctx.data["pending"] = items


def budget_line(exc: BudgetReached, budget_usd: float | None) -> str:
    line = "BUDGET REACHED: spent %s of %s." % (fmt_usd(exc.spent_micro), fmt_usd(exc.budget_micro))
    if exc.pending_micro:
        return (
            line + " The %s of queued call(s) listed above still fit; make them and ingest them. "
            "Nothing beyond them will be queued." % fmt_usd(exc.pending_micro)
        )
    return line + " Progress is saved; raise budget_usd in the brief to continue."


BALANCE_MESSAGE = (
    "Your treg balance is empty. Top up at treg.to -> Team -> Billing, then re-run the "
    "same command; finished work is cached."
)
CAP_MESSAGE = (
    "Your treg token hit its daily call limit. It resets tomorrow, or raise the limit at "
    "treg.to -> Team -> agent tokens, then re-run the same command; finished work is cached."
)


def flush(ctx: Ctx, command: str, code: int) -> None:
    if ctx.as_json:
        payload: dict[str, Any] = {"ok": code == 0, "exit": code, "command": command}
        payload.update(ctx.data)
        if ctx.notes:
            payload["notes"] = [redact(n) for n in ctx.notes]
        print(redact(json.dumps(payload, ensure_ascii=False)))
        return
    out = ctx.lines + [n for n in ctx.notes]
    if out:
        print(redact("\n".join(out)))


def short(text: Any, n: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "..."


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_init(ctx: Ctx, a: argparse.Namespace) -> int:
    created: list[str] = []
    ctx.home.mkdir(parents=True, exist_ok=True)
    ensure_home(ctx.home)
    for name, header in (("exclusions.csv", "kind,value,reason"), ("seen.csv", "domain,email,run,ts")):
        p = ctx.home / name
        if not p.exists():
            write_text(p, header + "\n")
            created.append(name)
    ctx.say("home: %s" % ctx.home)
    ctx.say("created: %s" % (", ".join(created) if created else "nothing new (already initialized)"))
    ctx.data.update({"home": str(ctx.home), "created": created})
    return EXIT_OK


def cmd_config(ctx: Ctx, a: argparse.Namespace) -> int:
    if a.token_stdin and a.token_env:
        raise UsageError("use only one of --token-stdin and --token-env")
    token = ""
    if a.token_stdin:
        token = sys.stdin.read().strip()
        if not token:
            raise UsageError("no token received on stdin")
    elif a.token_env:
        token = os.environ.get(a.token_env, "").strip()
        if not token:
            raise UsageError("environment variable %s is not set or empty" % a.token_env)
    if not (token or a.transport or a.base_url):
        raise UsageError("nothing to configure: give --token-stdin, --token-env, --transport or --base-url")
    if a.base_url and not re.match(r"^https?://[^\s/]+", a.base_url):
        raise UsageError("--base-url must start with http:// or https://")
    cfg = load_config(ctx.home)
    if token:
        cfg["token"] = token
        _SECRETS.add(token)
        ctx.token = token
    if a.base_url:
        cfg["base_url"] = a.base_url.rstrip("/")
    cfg.setdefault("base_url", DEFAULT_BASE_URL)
    if a.transport:
        cfg["transport"] = a.transport
    else:
        cfg.setdefault("transport", "http" if cfg.get("token") else "cli")
    cfg.setdefault("created", now_iso())
    ctx.home.mkdir(parents=True, exist_ok=True)
    write_text(ctx.home / "config.json", json.dumps(cfg, indent=2) + "\n", mode=0o600, scrub=False)
    ctx.say("config saved: %s" % (ctx.home / "config.json"))
    ctx.say("transport: %s" % cfg["transport"])
    ctx.say("token: %s" % ("stored (not shown)" if cfg.get("token") else "not set"))
    ctx.data.update({"transport": cfg["transport"], "token_set": bool(cfg.get("token"))})
    return EXIT_OK


def ledger_totals(home: Path, run: str | None = None) -> dict[str, Any]:
    rows = read_ledger(home)
    today = now_iso()[:10]
    total = sum(to_int(r.get("charged_micro"), 0) for r in rows)
    today_micro = sum(
        to_int(r.get("charged_micro"), 0) for r in rows if str(r.get("ts", ""))[:10] == today
    )
    out: dict[str, Any] = {
        "calls": len(rows), "total_micro": total, "today_micro": today_micro,
        "cache_hits": sum(1 for r in rows if r.get("cache_hit")),
    }
    if run is not None:
        by: dict[str, dict[str, int]] = {}
        for r in rows:
            if r.get("run") != run:
                continue
            e = by.setdefault(str(r.get("endpoint")), {"calls": 0, "micro": 0, "cache_hits": 0})
            e["calls"] += 1
            e["micro"] += to_int(r.get("charged_micro"), 0)
            e["cache_hits"] += 1 if r.get("cache_hit") else 0
        out["run_by_endpoint"] = by
        out["run_micro"] = sum(v["micro"] for v in by.values())
        out["run_cache_hits"] = sum(v["cache_hits"] for v in by.values())
    return out


def cmd_doctor(ctx: Ctx, a: argparse.Namespace) -> int:
    cfg = load_config(ctx.home)
    treg = find_treg()
    ctx.say("lead-finder engine %s" % VERSION)
    ctx.say("python: %s" % sys.version.split()[0])
    ctx.say("home: %s" % ctx.home)
    ctx.say("transport: %s" % ctx.transport)
    ctx.say("token set: %s" % ("yes" if cfg.get("token") else "no"))
    ctx.say("treg CLI: %s" % (("found at %s" % treg) if treg else "not found"))
    code = EXIT_OK
    live = "skipped"
    if ctx.transport == "ingest":
        ctx.say("live call: skipped (ingest mode has no network; Claude uses the treg MCP tool)")
    else:
        was_fresh = ctx.fresh
        ctx.fresh = True
        try:
            env = call(EP_SEARCH, params={"query": "lead finder test", "domain_type": "web"},
                       stage="other", ctx=ctx)
            status = env_status(env)
            if env_ok(env):
                n = len(result_of(env).get("results") or [])
                live = "OK"
                ctx.say("live call: OK (%s, http %d, %d results, %s)" % (
                    EP_SEARCH, status, n, fmt_usd(to_int(env["_treg"].get("charged_micro")))))
            else:
                live = "FAIL"
                ctx.say("live call: FAIL (http %d)" % status)
                code = EXIT_TRANSPORT
        except TransportUnavailable as exc:
            live = "FAIL"
            ctx.say("live call: FAIL (%s)" % redact(exc))
            code = EXIT_TRANSPORT
        except TransportError as exc:
            live = "FAIL"
            ctx.say("live call: FAIL (%s)" % redact(exc))
            code = EXIT_TRANSPORT
        except OutOfBalance:
            live = "FAIL"
            ctx.say("live call: FAIL (balance empty)")
            ctx.notes.append(BALANCE_MESSAGE)
            code = EXIT_BALANCE
        except CallCapReached:
            live = "FAIL"
            ctx.say("live call: FAIL (daily call limit reached)")
            ctx.notes.append(CAP_MESSAGE)
            code = EXIT_CAP
        finally:
            ctx.fresh = was_fresh
    totals = ledger_totals(ctx.home)
    ctx.say("ledger: %d call(s), %s total, %d cache hit(s)" % (
        totals["calls"], fmt_usd(totals["total_micro"]), totals["cache_hits"]))
    ctx.data.update({
        "python": sys.version.split()[0], "home": str(ctx.home), "transport": ctx.transport,
        "token_set": bool(cfg.get("token")), "cli_found": bool(treg), "live_call": live,
        "ledger_calls": totals["calls"], "ledger_total_micro": totals["total_micro"],
    })
    return code


def cmd_brief_check(ctx: Ctx, a: argparse.Namespace) -> int:
    check_slug_arg(a.slug)
    path = ctx.home / "runs" / a.slug / "brief.json"
    if not path.exists():
        ctx.say("problem: %s does not exist" % path)
        ctx.data.update({"ok_brief": False, "problems": ["brief.json is missing"]})
        return EXIT_USAGE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ctx.say("problem: brief.json is not valid JSON (%s)" % exc)
        ctx.data.update({"ok_brief": False, "problems": ["brief.json is not valid JSON"]})
        return EXIT_USAGE
    problems = check_brief(data, a.slug)
    if problems:
        for p in problems:
            ctx.say("problem: %s" % p)
        ctx.say("%d problem(s) found. Fix them all, then run brief-check again." % len(problems))
        ctx.data.update({"ok_brief": False, "problems": problems})
        return EXIT_USAGE
    ctx.say("brief OK: %s (recipe %s, target %d, budget $%.2f, %d queries)" % (
        a.slug, data["recipe"], data["target_count"], data["budget_usd"], len(data["queries"])))
    ctx.data.update({"ok_brief": True, "problems": []})
    return EXIT_OK


def cmd_estimate(ctx: Ctx, a: argparse.Namespace) -> int:
    brief = load_brief(ctx, a.slug)
    assert brief is not None
    rows = load_candidates(ctx.run_dir)
    n = len(rows) if rows else int(math.ceil(brief["target_count"] * 1.5))
    q = len(brief["queries"])
    people_attempts = 1.5
    second_opinion = 0.3
    tp = TYPICAL_PRICES
    lines = [
        ("search", "%d queries x %s" % (q, "$%.4f" % tp[EP_SEARCH]), q * tp[EP_SEARCH]),
        ("contacts", "%d candidates x %.1f attempts x $%.4f" % (n, people_attempts, tp[EP_PEOPLE]),
         n * people_attempts * tp[EP_PEOPLE]),
        ("emails", "%d candidates x $%.4f" % (n, tp[EP_FIND]), n * tp[EP_FIND]),
        ("verify", "%d emails x $%.4f" % (n, tp[EP_VERIFY]), n * tp[EP_VERIFY]),
        ("verify (second opinion)",
         "%d x %d%% x $%.4f" % (n, int(second_opinion * 100), tp[EP_BOUNCEBAN]),
         n * second_opinion * tp[EP_BOUNCEBAN]),
    ]
    total = sum(x[2] for x in lines)
    budget = float(brief["budget_usd"])
    ctx.say("estimate for %s (assumes %d candidates%s, typical measured prices)" % (
        a.slug, n, "" if rows else ", 1.5 per wanted lead"))
    for stage, basis, cost in lines:
        ctx.say("  %-24s %-44s $%.4f" % (stage, basis, cost))
    ctx.say("  %-24s %-44s $%.4f" % ("total", "", total))
    ctx.say("budget: $%.2f%s" % (budget, "  -> ESTIMATE IS OVER BUDGET" if total > budget else ""))
    ctx.say("The hard cap uses higher worst-case prices per call, so it can stop a stage a little "
            "early. Cached repeats and free search/fetch calls cost nothing. Wait for the user's go.")
    ctx.data.update({
        "candidates_assumed": n, "estimate_usd": round(total, 6), "budget_usd": budget,
        "stages": [{"stage": s, "basis": b, "usd": round(c, 6)} for s, b, c in lines],
        "over_budget": total > budget,
    })
    return EXIT_OK


def domain_of_url(url: str) -> str:
    return host_of(url)


def cmd_search(ctx: Ctx, a: argparse.Namespace) -> int:
    brief = load_brief(ctx, a.slug)
    assert brief is not None
    run_dir = ctx.run_dir
    hits_path = run_dir / "hits.jsonl"
    seen_urls: set[str] = set()
    if hits_path.exists():
        for line in hits_path.read_text(encoding="utf-8").splitlines():
            try:
                seen_urls.add(str(json.loads(line).get("url")))
            except (ValueError, AttributeError):
                continue
    new_hits: list[dict[str, Any]] = []
    done = 0
    for q in brief["queries"]:
        params: dict[str, Any] = {"query": q["q"], "domain_type": "web"}
        for opt in ("location", "after_date", "page"):
            if q.get(opt) not in (None, ""):
                params[opt] = q[opt]
        env, err = safe_call(ctx, EP_SEARCH, method="GET", params=params, stage="search")
        if env is None or not env_ok(env):
            continue
        done += 1
        for r in result_of(env).get("results") or []:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            hit = {
                "query": q["q"], "title": r.get("title") or "", "url": url,
                "snippet": r.get("snippet") or "", "date": r.get("date") or "",
                "site_name": r.get("site_name") or "", "domain": domain_of_url(url),
            }
            new_hits.append(hit)
            append_text(hits_path, json.dumps(sanitize(hit), ensure_ascii=False) + "\n")
    ctx.say("search: %d of %d queries answered, %d new hit(s), %d total" % (
        done, len(brief["queries"]), len(new_hits), len(seen_urls)))
    for i, h in enumerate(new_hits[:HITS_PRINT_LIMIT], 1):
        ctx.say("%3d  %s  %s  %s  %s" % (
            i, short(h["title"], 60), h["domain"], h["date"] or "-", h["url"]))
    if len(new_hits) > HITS_PRINT_LIMIT:
        ctx.say("... %d more in %s" % (len(new_hits) - HITS_PRINT_LIMIT, hits_path))
    ctx.data.update({"queries_answered": done, "new_hits": len(new_hits), "total_hits": len(seen_urls),
                     "hits_file": str(hits_path), "hits": new_hits[:HITS_PRINT_LIMIT]})
    return _stage_exit(ctx)


def _stage_exit(ctx: Ctx) -> int:
    if ctx.pending:
        return EXIT_INGEST
    if ctx.transport_errors and ctx.ok_calls == 0:
        ctx.notes.append("No treg call could be completed. Run doctor to check the transport.")
        return EXIT_TRANSPORT
    return EXIT_OK


def cmd_fetch(ctx: Ctx, a: argparse.Namespace) -> int:
    check_slug_arg(a.slug)
    load_brief(ctx, a.slug, required=False)
    ctx.run = a.slug
    run_dir = ctx.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    urls: list[str] = []
    if a.urls:
        urls = [u.strip() for u in a.urls.split(",") if u.strip()]
    elif a.from_candidates:
        for row in load_candidates(run_dir):
            if row.get("status") == "excluded":
                continue
            if row.get("event_url"):
                urls.append(str(row["event_url"]))
            urls.extend(str(u) for u in (row.get("source_urls") or []))
    else:
        raise UsageError("give --urls U1,U2 or --from-candidates")
    seen: set[str] = set()
    clean: list[str] = []
    for u in urls:
        if not re.match(r"^https?://", u, re.I):
            raise UsageError("not an http(s) URL: %s" % short(u, 80))
        if u not in seen:
            seen.add(u)
            clean.append(u)
    if not clean:
        raise UsageError("no URLs to fetch")
    grep = None
    if a.grep:
        try:
            grep = re.compile(a.grep, re.I)
        except re.error as exc:
            raise UsageError("bad --grep regex: %s" % exc)
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    n = 0
    for i in range(0, len(clean), 10):
        batch = clean[i:i + 10]
        env, err = safe_call(
            ctx, EP_FETCH, method="POST", body={"urls": batch, "format": "markdown"}, stage="fetch")
        if env is None:
            continue
        if not env_ok(env):
            errors.append("batch of %d url(s): http %d" % (len(batch), env_status(env)))
            continue
        res = result_of(env)
        for r in res.get("results") or []:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url") or r.get("final_url") or "")
            text = str(r.get("text") or "")
            if not url:
                continue
            n += 1
            page_path = run_dir / "pages" / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".md")
            write_text(page_path, "<!-- url: %s -->\n%s\n" % (url, text))
            host = host_of(str(r.get("final_url") or url))
            emails: list[str] = []
            for m in EMAIL_RE.findall(text):
                e = m.strip(".").lower()
                if same_domain(e.rsplit("@", 1)[-1], host) and e not in emails:
                    emails.append(e)
            matches: list[str] = []
            if grep:
                for line in text.splitlines():
                    if grep.search(line):
                        matches.append(short(line, 240))
                        if len(matches) >= 12:
                            break
            page = {"url": url, "title": str(r.get("title") or ""), "chars": len(text),
                    "emails": emails, "grep": matches, "file": str(page_path)}
            pages.append(page)
            ctx.say("[%d] %s" % (n, url))
            ctx.say("    title: %s | chars: %d | saved: %s" % (short(page["title"], 80), len(text), page_path))
            ctx.say("    same-domain emails: %s" % (", ".join(emails) if emails else "none"))
            for m in matches:
                ctx.say("    > %s" % m)
        for e in res.get("errors") or []:
            errors.append(short(json.dumps(e) if not isinstance(e, str) else e, 200))
    for e in errors:
        ctx.say("ERROR: %s" % e)
    ctx.say("fetched %d page(s), %d error(s)" % (len(pages), len(errors)))
    ctx.data.update({"pages": pages, "errors": errors})
    return _stage_exit(ctx)


def cmd_add(ctx: Ctx, a: argparse.Namespace) -> int:
    load_brief(ctx, a.slug, required=False)
    ctx.run = a.slug
    if bool(a.json_rows) == bool(a.file):
        raise UsageError("give exactly one of --json or --file")
    items: list[Any] = []
    try:
        if a.json_rows:
            parsed = json.loads(a.json_rows)
            items = parsed if isinstance(parsed, list) else [parsed]
        else:
            text = Path(a.file).read_text(encoding="utf-8")
            if text.lstrip().startswith("["):
                items = json.loads(text)
            else:
                items = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    except (OSError, ValueError) as exc:
        raise UsageError("could not read rows: %s" % exc)
    run_dir = ctx.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = load_candidates(run_dir)
    have = {norm_domain(r.get("domain")) for r in rows}
    added: list[str] = []
    rejected: list[str] = []
    dropped: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            rejected.append("row is not a JSON object")
            continue
        domain = norm_domain(item.get("domain"))
        if not domain or not DOMAIN_RE.match(domain):
            rejected.append("%s: missing or invalid domain" % short(item.get("org") or "row", 40))
            continue
        if domain in have:
            rejected.append("%s: duplicate domain, already a candidate" % domain)
            continue
        row = new_row(domain)
        try:
            for k, v in item.items():
                if k in CAND_FIELDS and k != "domain":
                    row[k] = coerce_field(k, v)
        except UsageError as exc:
            rejected.append("%s: %s" % (domain, exc))
            continue
        if row["status"] not in ADD_STATUSES:
            rejected.append("%s: status %r cannot be set on add; verified, risky and dead come "
                            "from the verify command" % (domain, row["status"]))
            continue
        if row["email_check"]:
            rejected.append("%s: email_check is written by the verify command, not by add" % domain)
            continue
        row["verify_detail"] = {}
        row["find_verified"] = None
        was_excluded = row["status"] == "excluded"
        apply_email_rules(row)
        if row["status"] == "excluded" and not was_excluded:
            dropped.append("%s: free-mail email removed, row excluded" % domain)
        refresh_status(row)
        rows.append(row)
        have.add(domain)
        added.append(domain)
    save_candidates(run_dir, rows)
    ctx.say("added %d row(s), rejected %d. Candidates: %d." % (len(added), len(rejected), len(rows)))
    for r in rejected:
        ctx.say("rejected: %s" % r)
    for d in dropped:
        ctx.say("excluded: %s" % d)
    ctx.data.update({"added": added, "rejected": rejected, "excluded": dropped, "candidates": len(rows)})
    return EXIT_USAGE if rejected else EXIT_OK


def cmd_set(ctx: Ctx, a: argparse.Namespace) -> int:
    load_brief(ctx, a.slug, required=False)
    ctx.run = a.slug
    domain = norm_domain(a.domain)
    rows = load_candidates(ctx.run_dir)
    row = next((r for r in rows if norm_domain(r.get("domain")) == domain), None)
    if row is None:
        raise UsageError("no candidate with domain %s in %s" % (domain, a.slug))
    updates: dict[str, Any] = {}
    for pair in a.pairs:
        if "=" not in pair:
            raise UsageError("expected key=value, got %r" % short(pair, 40))
        key, _, val = pair.partition("=")
        key = key.strip()
        if key not in CAND_FIELDS or key == "domain":
            raise UsageError("cannot set %r (valid: %s)" % (
                key, ", ".join(k for k in CAND_FIELDS if k != "domain")))
        updates[key] = coerce_field(key, val)
    if "status" in updates and updates["status"] not in SET_STATUSES:
        raise UsageError(
            "status must be one of: %s. verified and risky are set only by the verify command."
            % ", ".join(SET_STATUSES))
    if updates.get("email_check"):
        raise UsageError("email_check is written only by the verify command. To redo a check, "
                         "clear it with email_check= and run verify.")
    old_email = str(row.get("email") or "")
    old_contact = str(row.get("contact_name") or "")
    row.update(updates)
    if "email" in updates:
        apply_email_rules(row)
    changed = row["email"] != old_email or str(row.get("contact_name") or "") != old_contact
    broken = row.get("status") in ("verified", "risky") and not row["email"]
    if changed or broken or "email_check" in updates:
        # A different person or address, or an explicit clear, voids the earlier check and its trail.
        row["email_check"] = ""
        row["verify_detail"] = {}
        if changed or broken:
            row["find_verified"] = None
        if not row["email"]:
            row["email_source"] = ""
            row["find_served_by"] = ""
        if row.get("status") in ("verified", "risky", "dead") and "status" not in updates:
            row["status"] = "ready"
    refresh_status(row)
    save_candidates(ctx.run_dir, rows)
    ctx.say("updated %s: %s (status %s)" % (domain, ", ".join(sorted(updates)), row["status"]))
    ctx.data.update({"domain": domain, "updated": sorted(updates), "status": row["status"]})
    return EXIT_OK


def cmd_screen(ctx: Ctx, a: argparse.Namespace) -> int:
    load_brief(ctx, a.slug, required=False)
    ctx.run = a.slug
    rows = load_candidates(ctx.run_dir)
    ex = read_csv_rows(ctx.home / "exclusions.csv")
    ex_domains: dict[str, str] = {}
    ex_emails: dict[str, str] = {}
    keywords: list[tuple[str, str]] = [(k, "intermediary: %s" % k) for k in INTERMEDIARY_KEYWORDS]
    for r in ex:
        kind = (r.get("kind") or "").strip().lower()
        val = (r.get("value") or "").strip()
        why = (r.get("reason") or "").strip()
        if not val or val.startswith("#"):
            continue
        if kind == "domain":
            ex_domains[norm_domain(val)] = why or "on exclusions list"
        elif kind == "email":
            ex_emails[val.lower()] = why or "on exclusions list"
        elif kind == "name_keyword":
            keywords.append((val.lower(), why or ("name keyword: %s" % val)))
    seen_domains: dict[str, str] = {}
    seen_emails: dict[str, str] = {}
    for r in read_csv_rows(ctx.home / "seen.csv"):
        if r.get("run") == a.slug:
            continue
        if r.get("domain"):
            seen_domains[norm_domain(r["domain"])] = r.get("run") or "earlier run"
        if r.get("email"):
            seen_emails[r["email"].strip().lower()] = r.get("run") or "earlier run"
    excluded: list[dict[str, str]] = []
    for row in rows:
        if row.get("status") not in ("new", "ready"):
            continue
        dom = norm_domain(row.get("domain"))
        email = str(row.get("email") or "").strip().lower()
        name = ("%s %s" % (row.get("org") or "", dom)).lower()
        reason = ""
        for d, why in ex_domains.items():
            if dom == d or dom.endswith("." + d):
                reason = "excluded domain: %s" % why
                break
        if not reason and dom in seen_domains:
            reason = "already contacted (seen, %s)" % seen_domains[dom]
        if not reason and email and email in seen_emails:
            reason = "email already seen (%s)" % seen_emails[email]
        if not reason:
            for kw, why in keywords:
                if kw and kw in name:
                    reason = why
                    break
        if not reason and email and is_freemail(email):
            reason = "free-mail email"
            row["email"] = ""
        if not reason and email and email in ex_emails:
            reason = "excluded email: %s" % ex_emails[email]
        if reason:
            row["status"] = "excluded"
            row["status_reason"] = reason
            excluded.append({"domain": dom, "org": str(row.get("org") or ""), "reason": reason})
        else:
            refresh_status(row)
    save_candidates(ctx.run_dir, rows)
    # Report every excluded row, including ones excluded earlier (by `add`, `set` or a prior screen).
    new_now = {e["domain"] for e in excluded}
    all_excluded = [
        {"domain": norm_domain(r.get("domain")), "org": str(r.get("org") or ""),
         "reason": str(r.get("status_reason") or "no reason recorded"),
         "new": norm_domain(r.get("domain")) in new_now}
        for r in rows if r.get("status") == "excluded"]
    ctx.say("screen: %d excluded of %d candidate(s) (%d new this pass)" % (
        len(all_excluded), len(rows), len(excluded)))
    for e in all_excluded:
        ctx.say("  excluded: %s | %s | %s%s" % (
            e["domain"], short(e["org"], 40), e["reason"], "" if e["new"] else " (earlier)"))
    ctx.data.update({"excluded": all_excluded, "newly_excluded": excluded, "candidates": len(rows)})
    return EXIT_OK


def people_from(env: dict[str, Any] | None) -> list[dict[str, Any]]:
    res = result_of(env)
    out = res.get("output") if isinstance(res.get("output"), dict) else res
    people = out.get("people") if isinstance(out, dict) else None
    return [p for p in (people or []) if isinstance(p, dict)]


def _sget(obj: Any, *path: str) -> str:
    """Walk nested dicts; return the value as a stripped string, or "" when not a scalar."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(key)
    if isinstance(cur, (str, int, float)) and not isinstance(cur, bool):
        return str(cur).strip()
    return ""


def _first(row: dict[str, Any], *paths: str) -> str:
    for path in paths:
        val = _sget(row, *path.split("."))
        if val:
            return val
    return ""


def normalize_person(row: Any, provider: str = "") -> dict[str, str] | None:
    """One row shape for the three people.search providers (contract section 5.1).

    Returns None when the row has no usable name.
    """
    if not isinstance(row, dict):
        return None
    first = _first(row, "first_name", "firstName", "profile.first_name")
    last = _first(row, "last_name", "lastName", "profile.last_name")
    full = _first(row, "full_name", "fullName", "name", "profile.full_name")
    if not full:
        full = ("%s %s" % (first, last)).strip()
    if not full:
        return None
    if not first and not last:
        first, last = split_name(full)
    country = _first(row, "location.country", "country")
    if not country:
        loc = row.get("location")
        if isinstance(loc, str) and loc.strip():
            country = loc.split(",")[-1].strip()
    return {
        "full_name": full,
        "first_name": first,
        "last_name": last,
        "title": _first(row, "title", "jobTitle", "job_title", "current_title",
                        "profile.title", "profile.headline"),
        "linkedin": _first(row, "employee_linkedin", "linkedin_url", "linkedinUrl", "linkedin",
                           "link.linkedin"),
        "country": country,
        "city": _first(row, "location.city"),
        "work_email": _first(row, "work_email", "email"),
        "provider": str(provider or ""),
    }


ROLE_KEYWORDS = ("event", "conference", "meeting", "program", "education",
                 "professional development", "speaker", "executive director",
                 "chief executive", "president")
US_NAMES = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}


def title_score(title: str, tier_a: list[str], fallback: list[str]) -> int:
    """2 = contains a tier-A title, 1 = contains a role keyword, 0 = unrelated."""
    low = (title or "").lower()
    if not low:
        return 0
    if any(t.strip().lower() in low for t in tier_a if t.strip()):
        return 2
    keywords = list(ROLE_KEYWORDS)
    if any("development" in t.lower() for t in fallback if isinstance(t, str)):
        keywords.append("development")
    return 1 if any(k in low for k in keywords) else 0


def rank_people(
    people: list[dict[str, str]], tier_a: list[str], fallback: list[str]
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for p in people:
        q: dict[str, Any] = dict(p)
        q["title_score"] = title_score(p.get("title", ""), tier_a, fallback)
        scored.append(q)
    scored.sort(key=lambda q: (
        -q["title_score"],
        0 if q.get("country", "").strip().lower() in US_NAMES else 1,
        q.get("full_name", "").lower(),
    ))
    return scored


def served_by_of(env: dict[str, Any] | None) -> str:
    if not env:
        return ""
    inner = result_of(env).get("_treg")
    inner_served = inner.get("served_by") if isinstance(inner, dict) else ""
    return str(env["_treg"].get("served_by") or inner_served or "")


def normalized_people(env: dict[str, Any] | None) -> list[dict[str, str]]:
    served = served_by_of(env)
    out: list[dict[str, str]] = []
    for row in people_from(env):
        person = normalize_person(row, served)
        if person:
            out.append(person)
    return out


MATCH_LABEL = {2: "A", 1: "kw", 0: "-"}


def cmd_contacts(ctx: Ctx, a: argparse.Namespace) -> int:
    brief = load_brief(ctx, a.slug)
    assert brief is not None
    rows = load_candidates(ctx.run_dir)
    titles = [t for t in (brief.get("titles_tier_a") or []) if isinstance(t, str) and t.strip()]
    fallback = [t for t in (brief.get("titles_fallback") or []) if isinstance(t, str)]
    only = norm_domain(a.domain) if a.domain else ""
    if only and not any(norm_domain(r.get("domain")) == only for r in rows):
        raise UsageError("no candidate with domain %s" % only)
    results: list[dict[str, Any]] = []
    for row in rows:
        dom = norm_domain(row.get("domain"))
        if only and dom != only:
            continue
        if not dom or row.get("contact_name"):
            continue
        if row.get("status") in ("excluded", "dead") and not only:
            continue
        people: list[dict[str, str]] = []
        matched = ""
        strict = False
        served = ""
        complete = True
        # Strict per-title calls first: only providers that honor `title` answer.
        for title in titles:
            body: dict[str, Any] = {"company_domain": dom, "title": title, "limit": 25,
                                    "country": "US"}
            env, err = safe_call(ctx, EP_PEOPLE, method="POST", body=body, stage="contacts",
                                 headers=STRICT_HEADERS)
            if env is None:
                complete = False
                break
            if not env_ok(env):
                # A strict call may be refused when no provider can honor the filter;
                # treat it as a miss and let the next title or the broad call try.
                ctx.notes.append("strict search for %s (%s) returned http %d; treated as a miss"
                                 % (dom, title, env_status(env)))
                continue
            found = normalized_people(env)
            if found:
                people, matched, strict, served = found, title, True, served_by_of(env)
                break
        if complete and not people:
            body = {"company_domain": dom, "limit": 25, "country": "US"}
            env, err = safe_call(ctx, EP_PEOPLE, method="POST", body=body, stage="contacts")
            if env is None or not env_ok(env):
                complete = False
            else:
                people, served = normalized_people(env), served_by_of(env)
        options = rank_people(people, titles, fallback)
        if complete:
            stored = {"options": options, "served_by": served, "strict": strict}
            write_text(ctx.run_dir / "people" / (dom + ".json"),
                       json.dumps(sanitize(stored), ensure_ascii=False, indent=1) + "\n")
        ctx.say("%s (%s): %s" % (dom, short(row.get("org"), 40),
                                 "%d option(s)" % len(options) if options else "no contacts found"))
        shown = []
        for i, p in enumerate(options[:10], 1):
            label = MATCH_LABEL[p["title_score"]]
            ctx.say("  %d. %s | %s | %s | %s | match:%s" % (
                i, p["full_name"], short(p["title"], 60) or "-", p["country"] or "-",
                p["linkedin"] or "-", label))
            shown.append({"n": i, "name": p["full_name"], "title": p["title"],
                          "country": p["country"], "linkedin": p["linkedin"], "match": label})
        no_role = bool(options) and options[0]["title_score"] == 0
        if no_role:
            ctx.say("no role match for %s: read the org's staff/about page with fetch --grep, "
                    "or skip" % dom)
        results.append({"domain": dom, "options": shown, "matched_title_query": matched,
                        "strict": strict, "no_role_match": no_role})
    ctx.say("Pick a contact per domain with: set <slug> <domain> contact_name=... contact_title=... "
            "contact_source=search linkedin=...")
    ctx.data.update({"contacts": results})
    return _stage_exit(ctx)


def split_name(full: str) -> tuple[str, str]:
    toks = [t for t in re.split(r"\s+", full.strip()) if t]
    while len(toks) > 2 and toks[-1].strip(".,").lower() in ("jr", "sr", "ii", "iii", "iv", "phd", "md", "cpa"):
        toks.pop()
    if len(toks) < 2:
        return (toks[0] if toks else ""), ""
    return toks[0], toks[-1]


def cmd_emails(ctx: Ctx, a: argparse.Namespace) -> int:
    load_brief(ctx, a.slug)
    rows = load_candidates(ctx.run_dir)
    found = missed = 0
    try:
        for row in rows:
            dom = norm_domain(row.get("domain"))
            if row.get("status") in ("excluded", "dead") or row.get("email"):
                continue
            if not row.get("contact_name") or not dom:
                continue
            first, last = split_name(str(row["contact_name"]))
            if not first or not last:
                row["status_reason"] = "contact_name needs a first and last name"
                continue
            body: dict[str, Any] = {
                "full_name": str(row["contact_name"]).strip(), "first_name": first,
                "last_name": last, "domain": dom,
            }
            if row.get("linkedin"):
                body["linkedin_url"] = row["linkedin"]
            env, err = safe_call(ctx, EP_FIND, method="POST", body=body, stage="emails")
            if env is None:
                continue
            if not env_ok(env):
                if env_status(env) == 402:
                    row["status_reason"] = "email lookup skipped: over the per-call price cap"
                else:
                    row["status_reason"] = "email lookup failed: http %d" % env_status(env)
                missed += 1
                continue
            out = output_of(env)
            email = out.get("email") if isinstance(out, dict) else None
            if isinstance(email, str) and "@" in email and not is_freemail(email):
                row["email"] = email.strip().lower()
                row["email_source"] = "find"
                v = out.get("verified")
                row["find_verified"] = v if isinstance(v, bool) else None
                inner = result_of(env).get("_treg")
                row["find_served_by"] = str(
                    (inner.get("served_by") if isinstance(inner, dict) else "")
                    or env["_treg"].get("served_by") or "")
                row["status_reason"] = ""
                refresh_status(row)
                found += 1
            else:
                row["status_reason"] = "email not found"
                missed += 1
    finally:
        save_candidates(ctx.run_dir, rows)
    ctx.say("emails: %d found, %d not found" % (found, missed))
    ctx.data.update({"found": found, "not_found": missed})
    return _stage_exit(ctx)


def parse_score(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def verify_row(ctx: Ctx, row: dict[str, Any]) -> str:
    """Apply rule D1 to one row. Returns "" or "ingest"/"network" when nothing was decided."""
    email = str(row["email"])
    env, err = safe_call(ctx, EP_VERIFY, method="POST", body={"email": email}, stage="verify")
    if env is None:
        if err == "network":
            row["status_reason"] = "verify failed: network error"
        return err
    if not env_ok(env):
        row["status_reason"] = "verify failed: http %d" % env_status(env)
        return "http"
    out = output_of(env)
    status = str(out.get("status") or "").strip().lower()
    valid = out.get("valid")
    detail: dict[str, Any] = {"verify_status": status, "verify_valid": valid if isinstance(valid, bool) else None}
    if valid is True or status in VALID_STATUSES:
        row["verify_detail"] = detail
        row["email_check"] = "Verified"
        row["status"] = "verified"
        row["status_reason"] = ""
        return ""
    if status in ACCEPT_ALL_STATUSES:
        benv, berr = safe_call(ctx, EP_BOUNCEBAN, method="GET", params={"email": email}, stage="verify")
        if benv is None:
            if berr == "network":
                row["status_reason"] = "verify failed: network error"
            return berr
        if not env_ok(benv):
            row["status_reason"] = "verify failed: bounceban http %d" % env_status(benv)
            return "http"
        bres = result_of(benv)
        bout = bres.get("output") if isinstance(bres.get("output"), dict) else bres
        verdict = str(bout.get("result") or "").strip().lower()
        score = parse_score(bout.get("score"))
        detail.update({"bounceban_result": verdict, "bounceban_score": score,
                       "is_accept_all": bout.get("is_accept_all")})
        row["verify_detail"] = detail
        label = "n/a" if score is None else str(score)
        if verdict == "deliverable" and score is not None and score >= BOUNCEBAN_MIN_SCORE:
            row["email_check"] = "Verified (accept-all, score %s)" % label
            row["status"] = "verified"
        else:
            row["email_check"] = "Risky (score %s)" % label
            row["status"] = "risky"
        row["status_reason"] = ""
        return ""
    if status in INVALID_STATUSES:
        row["verify_detail"] = detail
        row["email_check"] = "Invalid"
        row["status"] = "dead"
        row["status_reason"] = "email invalid"
        return ""
    row["status_reason"] = "verify returned an unrecognized status: %s" % (status or "none")
    return "unrecognized"


def cmd_verify(ctx: Ctx, a: argparse.Namespace) -> int:
    load_brief(ctx, a.slug)
    rows = load_candidates(ctx.run_dir)
    counts: Counter[str] = Counter()
    try:
        for row in rows:
            if not row.get("email") or row.get("email_check"):
                continue
            if row.get("status") in ("excluded", "dead"):
                continue
            verify_row(ctx, row)
            if row.get("email_check"):
                counts[str(row["status"])] += 1
    finally:
        save_candidates(ctx.run_dir, rows)
    pending_rows = sum(1 for r in rows if r.get("email") and not r.get("email_check")
                       and r.get("status") not in ("excluded", "dead"))
    ctx.say("verify: %d verified, %d risky, %d dead, %d not decided (re-run to retry)" % (
        counts["verified"], counts["risky"], counts["dead"], pending_rows))
    ctx.data.update({"verified": counts["verified"], "risky": counts["risky"],
                     "dead": counts["dead"], "undecided": pending_rows})
    return _stage_exit(ctx)


def _csv_cell(value: Any) -> str:
    s = "" if value is None else str(value)
    if s and s[0] in "=+@-" and not re.match(r"^-?\d", s):
        return "'" + s
    return s


def lead_row(n: int, r: dict[str, Any]) -> list[str]:
    return [str(n)] + [_csv_cell(x) for x in (
        r.get("org"), r.get("event"), r.get("event_date"), r.get("event_url"),
        r.get("cfp_deadline"), r.get("contact_name"), r.get("contact_title"),
        r.get("email"), r.get("email_check"), r.get("linkedin"), r.get("why_fit"),
        r.get("opener"))]


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple[int, str, int, str]:
        cfp = str(r.get("cfp_deadline") or "")
        ev = str(r.get("event_date") or "")
        return (1 if not cfp else 0, cfp, 1 if not ev else 0, ev)
    return sorted(rows, key=key)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(LEADS_COLUMNS)
    for i, r in enumerate(rows, 1):
        w.writerow(lead_row(i, r))
    write_text(path, buf.getvalue())


def cmd_export(ctx: Ctx, a: argparse.Namespace) -> int:
    brief = load_brief(ctx, a.slug)
    assert brief is not None
    run_dir = ctx.run_dir
    rows = load_candidates(run_dir)
    # A row is exported only with a real address and a check that verify wrote.
    verified = sort_rows([
        r for r in rows if r.get("status") == "verified" and str(r.get("email") or "").strip()
        and str(r.get("email_check") or "").startswith("Verified")])
    leads = verified[: int(brief["target_count"])]
    risky = sort_rows([
        r for r in rows if r.get("status") == "risky" and str(r.get("email") or "").strip()
        and str(r.get("email_check") or "").startswith("Risky")])
    write_csv(run_dir / "leads.csv", leads)
    write_csv(run_dir / "risky.csv", risky)

    hits = 0
    hp = run_dir / "hits.jsonl"
    if hp.exists():
        hits = sum(1 for ln in hp.read_text(encoding="utf-8").splitlines() if ln.strip())
    live = [r for r in rows if r.get("status") != "excluded"]
    funnel = [
        ("hits", hits), ("candidates", len(rows)), ("not excluded", len(live)),
        ("with contact", sum(1 for r in live if r.get("contact_name"))),
        ("with email", sum(1 for r in live if r.get("email"))),
        ("verified", len(verified)), ("exported", len(leads)),
    ]
    totals = ledger_totals(ctx.home, a.slug)
    by = totals.get("run_by_endpoint", {})
    md = ["# Lead Finder summary: %s" % a.slug, "",
          "Recipe: %s. Target: %d lead(s)." % (brief["recipe"], brief["target_count"]), "",
          "## Funnel", "", " -> ".join("%s %d" % (k, v) for k, v in funnel), "",
          "## Spend", "", "| Endpoint | Calls | Cache hits | Charged |", "|---|---|---|---|"]
    for ep in sorted(by):
        md.append("| %s | %d | %d | %s |" % (ep, by[ep]["calls"], by[ep]["cache_hits"], fmt_usd(by[ep]["micro"])))
    md += ["", "Total for this run: %s of a %s budget." % (
        fmt_usd(totals.get("run_micro", 0)), "$%.2f" % brief["budget_usd"]),
        "Cache hits this run: %d (free)." % totals.get("run_cache_hits", 0), "",
        "## Next steps", ""]
    steps = ["Open leads.csv, read each opener and edit it in your own words.",
             "Send from your own mailbox. This tool never sends anything."]
    if len(leads) < int(brief["target_count"]):
        steps.append("Only %d of %d target leads are verified. Run refine to widen the search; "
                     "cached results are free." % (len(leads), brief["target_count"]))
    if risky:
        steps.append("risky.csv has %d lead(s) whose email could not be fully verified. Send "
                     "only if you accept some bounce risk." % len(risky))
    md += ["%d. %s" % (i, s) for i, s in enumerate(steps, 1)]
    write_text(run_dir / "summary.md", "\n".join(md) + "\n")

    seen_path = ctx.home / "seen.csv"
    if not seen_path.exists():
        write_text(seen_path, "domain,email,run,ts\n")
    existing = {(r.get("domain"), r.get("email"), r.get("run")) for r in read_csv_rows(seen_path)}
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    ts = now_iso()
    appended = 0
    for r in leads:
        k = (norm_domain(r.get("domain")), str(r.get("email") or ""), a.slug)
        if k in existing:
            continue
        w.writerow([k[0], k[1], a.slug, ts])
        appended += 1
    if appended:
        text = seen_path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        write_text(seen_path, text + buf.getvalue())

    ctx.say("export: %d lead(s) in leads.csv, %d in risky.csv" % (len(leads), len(risky)))
    for i, r in enumerate(leads, 1):
        ctx.say("%2d. %s | %s | %s | %s | %s | %s" % (
            i, short(r.get("org"), 32), short(r.get("event"), 28), r.get("cfp_deadline") or "-",
            short(r.get("contact_name"), 22), r.get("email"), r.get("email_check")))
    ctx.say("leads: %s" % (run_dir / "leads.csv"))
    ctx.say("risky: %s" % (run_dir / "risky.csv"))
    ctx.say("summary: %s" % (run_dir / "summary.md"))
    ctx.data.update({"exported": len(leads), "risky": len(risky), "seen_appended": appended,
                     "leads_csv": str(run_dir / "leads.csv"), "risky_csv": str(run_dir / "risky.csv"),
                     "summary_md": str(run_dir / "summary.md"), "funnel": dict(funnel)})
    return EXIT_OK


def fetch_balance(ctx: Ctx) -> str:
    try:
        if ctx.transport == "cli":
            binary = find_treg()
            if not binary:
                return "unavailable"
            proc = subprocess.run([binary, "balance", "--json"], capture_output=True, text=True,
                                  timeout=30, check=False)
            data = json.loads(proc.stdout)
        elif ctx.transport == "http" and ctx.token:
            req = urllib.request.Request(
                ctx.base_url + "/balance",
                headers={"X-Treg-Token": ctx.token, "Accept": "application/json",
                         "User-Agent": "lead-finder/%s" % VERSION})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        else:
            return "unavailable"
        if isinstance(data, dict):
            if _is_num(data.get("balance_usd")):
                return "$%.4f" % data["balance_usd"]
            if _is_num(data.get("balance_micro")):
                return fmt_usd(int(data["balance_micro"]))
    except (OSError, ValueError, subprocess.SubprocessError, urllib.error.URLError):
        pass
    return "unavailable"


def cmd_spend(ctx: Ctx, a: argparse.Namespace) -> int:
    run = a.slug
    if run:
        check_slug_arg(run)
    totals = ledger_totals(ctx.home, run)
    if run:
        ctx.say("run %s: %s over %d call(s)" % (
            run, fmt_usd(totals.get("run_micro", 0)),
            sum(v["calls"] for v in totals.get("run_by_endpoint", {}).values())))
        for ep, v in sorted(totals.get("run_by_endpoint", {}).items()):
            ctx.say("  %-34s %s (%d call(s), %d cache hit(s))" % (
                ep, fmt_usd(v["micro"]), v["calls"], v["cache_hits"]))
    ctx.say("today: %s" % fmt_usd(totals["today_micro"]))
    ctx.say("all time: %s over %d ledger line(s)" % (fmt_usd(totals["total_micro"]), totals["calls"]))
    bal = fetch_balance(ctx)
    ctx.say("balance: %s" % bal)
    ctx.data.update({"today_micro": totals["today_micro"], "total_micro": totals["total_micro"],
                     "ledger_lines": totals["calls"], "balance": bal})
    if run:
        ctx.data.update({"run_micro": totals.get("run_micro", 0),
                         "run_by_endpoint": totals.get("run_by_endpoint", {})})
    return EXIT_OK


def cmd_ingest(ctx: Ctx, a: argparse.Namespace) -> int:
    check_slug_arg(a.slug, allow_dash=True)
    ctx.run = None if a.slug == "-" else a.slug
    if ctx.run:
        load_brief(ctx, a.slug, required=False)
    try:
        raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError("could not read %s as JSON: %s" % (a.file, exc))
    params = body = None
    try:
        if a.params:
            params = json.loads(a.params)
        if a.body:
            body = json.loads(a.body)
    except ValueError as exc:
        raise UsageError("--params/--body must be JSON: %s" % exc)
    if params is not None and not isinstance(params, dict):
        raise UsageError("--params must be a JSON object")
    cost: int | None = None
    if a.cost_usd is not None:
        if a.cost_usd < 0:
            raise UsageError("--cost-usd cannot be negative")
        cost = usd_to_micro(a.cost_usd)
    # No explicit cost and no charged_micro in the result: ledger the endpoint's expected
    # price, so the per-run cap still counts MCP calls (contract section 7.2).
    env = sanitize(normalize_env(raw, cost_micro=cost, default_micro=expected_micro(a.endpoint)))
    meth = endpoint_method(a.endpoint, body)
    key = cache_key(a.endpoint, meth, params or {}, body, STRICT_HEADERS if a.strict else None)
    ledger_append(ctx, a.stage, a.endpoint, meth, env["_treg"], False)
    status = to_int(env["_treg"].get("http_status"), 200)
    if 200 <= status < 300:
        cache_write(ctx.home, key, env)
    # The saved MCP result may hold phone numbers or personal email; scrub the source file too.
    try:
        write_text(Path(a.file), json.dumps(sanitize(raw), ensure_ascii=False))
    except OSError as exc:
        ctx.notes.append("could not scrub %s: %s" % (a.file, redact(exc)))
    charged = to_int(env["_treg"].get("charged_micro"), 0)
    ctx.say("ingested %s (http %d, %s) into the cache; %s was scrubbed of phone and personal email" % (
        a.endpoint, status, fmt_usd(charged), a.file))
    ctx.data.update({"endpoint": a.endpoint, "http_status": status, "cached": 200 <= status < 300})
    return EXIT_OK


def cmd_status(ctx: Ctx, a: argparse.Namespace) -> int:
    check_slug_arg(a.slug)
    ctx.run = a.slug
    if not ctx.run_dir.exists():
        raise UsageError("no run folder for %s" % a.slug)
    brief_path = ctx.run_dir / "brief.json"
    brief = None
    if brief_path.exists():
        try:
            parsed = json.loads(brief_path.read_text(encoding="utf-8"))
            brief = parsed if isinstance(parsed, dict) else None
        except ValueError:
            brief = None
    rows = load_candidates(ctx.run_dir)
    counts = Counter(str(r.get("status")) for r in rows)
    spent = run_spent_micro(ctx.home, a.slug)
    budget = brief.get("budget_usd") if brief else None
    ctx.say("run: %s" % a.slug)
    ctx.say("candidates: %d (%s)" % (
        len(rows), ", ".join("%s %d" % (k, counts[k]) for k in STATUSES if counts[k]) or "none"))
    ctx.say("spend: %s%s" % (fmt_usd(spent), (" of $%.2f" % budget) if _is_num(budget) else ""))
    live = [r for r in rows if r.get("status") not in ("excluded", "dead")]
    me = lf_prefix(ctx)
    if not brief or check_brief(brief, a.slug):
        nxt = "write brief.json, then: %s brief-check %s" % (me, a.slug)
    elif not (ctx.run_dir / "hits.jsonl").exists() and not rows:
        nxt = "%s search %s" % (me, a.slug)
    elif not rows:
        nxt = "screen the hits, fetch pages, then add candidates with: %s add %s --json '{...}'" % (me, a.slug)
    elif any(r.get("status") == "new" and not r.get("contact_name") for r in live):
        nxt = "%s screen %s, then %s contacts %s" % (me, a.slug, me, a.slug)
    elif any(r.get("contact_name") and not r.get("email") for r in live):
        nxt = "%s emails %s" % (me, a.slug)
    elif any(r.get("email") and not r.get("email_check") for r in live):
        nxt = "%s verify %s" % (me, a.slug)
    elif _export_is_current(ctx.run_dir) and (counts["verified"] or counts["risky"]):
        nxt = ("exported: leads.csv is current. Next: /lead-finder:draft %s for first notes, or "
               "/lead-finder:refine %s to adjust the search" % (a.slug, a.slug))
    elif counts["verified"] or counts["risky"]:
        nxt = "write openers (set <domain> opener=...), then %s export %s" % (me, a.slug)
    else:
        nxt = "review candidates; nothing is ready to export yet"
    ctx.say("next: %s" % nxt)
    ctx.data.update({"counts": dict(counts), "candidates": len(rows), "spent_micro": spent,
                     "budget_usd": budget, "next": nxt})
    return EXIT_OK


def _export_is_current(run_dir: Path) -> bool:
    try:
        return (run_dir / "leads.csv").stat().st_mtime_ns >= (run_dir / "candidates.jsonl").stat().st_mtime_ns
    except OSError:
        return False


def lf_prefix(ctx: Ctx) -> str:
    return "python3 %s --home %s" % (shlex.quote(str(SELF)), shlex.quote(str(ctx.home)))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

STAGE_COMMANDS = {"search", "fetch", "contacts", "emails", "verify"}


def build_parser() -> argparse.ArgumentParser:
    def common(default: Any, with_json: bool = True) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--home", default=default, metavar="PATH", help="working folder")
        p.add_argument("--transport", choices=TRANSPORTS, default=default)
        p.add_argument("--fresh", action="store_true", default=default, help="bypass cache reads")
        if with_json:
            p.add_argument("--json", action="store_true", default=default,
                           help="machine-readable output")
        p.add_argument("--max-cost", type=float, default=default, metavar="USD",
                       help="per-call max-cost header override (capped at 0.05)")
        p.add_argument("--allow-expensive", action="store_true", default=default,
                       help="lift the 0.05 per-call ceiling")
        return p

    parser = argparse.ArgumentParser(
        prog="lf.py", description="Lead Finder engine.", parents=[common(None)])
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    shared = common(argparse.SUPPRESS)
    shared_no_json = common(argparse.SUPPRESS, with_json=False)

    def add(name: str, func: Any, help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(
            name, parents=[shared_no_json if name == "add" else shared],
            help=help_text, description=help_text)
        sp.set_defaults(func=func)
        return sp

    add("init", cmd_init, "create the home folder")
    sp = add("config", cmd_config, "write config.json (token via stdin or env only)")
    sp.add_argument("--token-stdin", action="store_true")
    sp.add_argument("--token-env", metavar="VAR")
    sp.add_argument("--base-url")
    add("doctor", cmd_doctor, "check python, transport, token and one free live call")
    for name, func, text in (
        ("brief-check", cmd_brief_check, "validate brief.json"),
        ("estimate", cmd_estimate, "estimate cost from the brief"),
        ("search", cmd_search, "run the brief queries"),
        ("screen", cmd_screen, "apply exclusions"),
        ("emails", cmd_emails, "find work emails"),
        ("verify", cmd_verify, "verify emails (rule D1)"),
        ("export", cmd_export, "write leads.csv, risky.csv, summary.md"),
        ("status", cmd_status, "counts and the next step"),
    ):
        add(name, func, text).add_argument("slug")
    sp = add("fetch", cmd_fetch, "fetch pages")
    sp.add_argument("slug")
    sp.add_argument("--urls")
    sp.add_argument("--from-candidates", action="store_true")
    sp.add_argument("--grep")
    sp = add("add", cmd_add, "add candidate rows")
    sp.add_argument("slug")
    sp.add_argument("--json", dest="json_rows", default=None)
    sp.add_argument("--file")
    sp = add("set", cmd_set, "update fields on one candidate")
    sp.add_argument("slug")
    sp.add_argument("domain")
    sp.add_argument("pairs", nargs="+", metavar="key=value")
    sp = add("contacts", cmd_contacts, "list contact options per candidate")
    sp.add_argument("slug")
    sp.add_argument("--domain")
    sp = add("spend", cmd_spend, "ledger totals and balance")
    sp.add_argument("slug", nargs="?")
    sp = add("ingest", cmd_ingest, "save an MCP result into the cache and ledger")
    sp.add_argument("slug")
    sp.add_argument("--stage", choices=STAGES, required=True)
    sp.add_argument("--endpoint", required=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--params")
    sp.add_argument("--body")
    sp.add_argument("--cost-usd", type=float, default=None)
    sp.add_argument("--strict", action="store_true",
                    help="the call carried X-Treg-Route-Strict-Filters: 1 (separate cache entry)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 2)
    home_arg = getattr(args, "home", None) or os.environ.get("LEAD_FINDER_HOME") or "lead-finder"
    home = Path(home_arg).expanduser().resolve()
    cfg = load_config(home)
    token = str(cfg.get("token") or "")
    ctx = Ctx(
        home=home,
        transport=resolve_transport(getattr(args, "transport", None), cfg),
        fresh=bool(getattr(args, "fresh", False)),
        as_json=bool(getattr(args, "json", False)),
        max_cost=getattr(args, "max_cost", None),
        allow_expensive=bool(getattr(args, "allow_expensive", False)),
        token=token,
        base_url=str(cfg.get("base_url") or DEFAULT_BASE_URL),
    )
    set_ctx(ctx)
    code = EXIT_OK
    try:
        if args.command not in ("init", "config") and not home.exists():
            home.mkdir(parents=True, exist_ok=True)
        code = args.func(ctx, args)
    except UsageError as exc:
        eprint("error: %s" % exc)
        code = EXIT_USAGE
    except TransportUnavailable as exc:
        eprint("error: %s" % exc)
        code = EXIT_TRANSPORT
    except BudgetReached as exc:
        ctx.notes.append(budget_line(exc, ctx.budget_usd))
        code = EXIT_BUDGET
    except OutOfBalance:
        ctx.notes.append(BALANCE_MESSAGE)
        code = EXIT_BALANCE
    except CallCapReached:
        ctx.notes.append(CAP_MESSAGE)
        code = EXIT_CAP
    except KeyboardInterrupt:
        eprint("interrupted")
        code = 130
    except Exception as exc:  # noqa: BLE001 - last-resort guard, message is redacted
        eprint("error: %s: %s" % (type(exc).__name__, exc))
        code = 1
    if ctx.pending:
        add_pending_output(ctx)
        if code in (EXIT_OK, EXIT_BUDGET):
            code = EXIT_INGEST
    flush(ctx, args.command, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
