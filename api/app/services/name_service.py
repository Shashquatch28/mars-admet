"""`POST /name` (frontend ADR-043) - the name of a molecule, from PubChem, looked up by InChIKey.

What leaves the server is the molecule's standard InChIKey and nothing else (never the SMILES, never anything about the user):
`ml/serve/inchikey.py` computes it with RDKit. What comes back is only what PubChem says for that key - its title, its computed
IUPAC name and the first few synonyms it lists - with the source and the record id kept beside it. Nothing is guessed from the
structure, and a molecule PubChem has no record of is `not_found`, never a made-up name.

A slow or broken source must never slow `/predict` or anything else, so the lookup has four guards: a short timeout on each
request, a ceiling on how fast this process asks (PubChem asks callers for 5 a second at most), a circuit breaker that stops
asking for a while after repeated failures, and one shared flight per key so ten copies of one molecule ask once. Every one of
them ends in an `unavailable` answer with the reason in words; a failure is told apart from "no record" so a client never shows
one as the other.

PubChem is one implementation of "a place that names structures". The route and the contract say nothing PubChem-specific, so
the local database planned for the next version can replace `lookup_pubchem` without a contract change.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from mars_contracts import NameResponse, NameStatus

from app.core.config import get_settings

name_available = False
try:
    _ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from serve.inchikey import inchikey  # noqa: E402

    name_available = True
except ImportError:

    def inchikey(smiles: str) -> str:  # pragma: no cover - only reached without rdkit, where the route 501s first
        raise RuntimeError("rdkit is not installed in this environment")


SOURCE = "PubChem"
# Part of the cache key: change it whenever what is stored or how it is chosen changes, so an older entry is never served as new.
NAME_VERSION = "n1"
_RECORD_URL = "https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
_USER_AGENT = "MARS-ADMET name lookup (InChIKey only)"

# A synonym that is only a registry number or a database id (50-78-2, CHEMBL25, DTXSID..., NSC-27223, EC 200-064-1) is a
# reference, not a name. Names have lowercase letters or no digits at all; these have digits and no lowercase.
_IDENTIFIER = re.compile(r"^(?=.*\d)[^a-z]*$")


@dataclass(frozen=True)
class Lookup:
    response: NameResponse
    cacheable: bool  # found and not_found are kept; unavailable, and a found without its synonyms, are not


class SourceError(Exception):
    """The source could not answer. `reason` is for a person; whether it counts against the breaker is `counts`."""

    def __init__(self, reason: str, *, counts: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.counts = counts


class Breaker:
    """Closed until `failures` requests in a row fail, then open for `open_seconds` (every lookup answers at once), then one
    probe: success closes it, failure opens it again. In-process: each API instance learns for itself that the source is down,
    which costs a few failed requests per instance and no shared state."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0
        self._probing = False

    def allow(self) -> bool:
        if self._failures < get_settings().name_breaker_failures:
            return True
        if self._clock() < self._open_until:
            return False
        if self._probing:
            return False
        self._probing = True
        return True

    def success(self) -> None:
        self._failures = 0
        self._probing = False

    def release(self) -> None:
        """A request that was allowed but never sent says nothing about the source; it must not hold the probe."""
        self._probing = False

    def failure(self) -> None:
        self._failures += 1
        self._probing = False
        if self._failures >= get_settings().name_breaker_failures:
            self._open_until = self._clock() + get_settings().name_breaker_open_seconds

    @property
    def is_open(self) -> bool:
        return self._failures >= get_settings().name_breaker_failures and self._clock() < self._open_until


class Throttle:
    """Spaces this process's requests to the source at least 1/rate seconds apart. A request that would have to wait longer than
    `budget` is refused (`SourceError`) rather than queued, so a burst of lookups answers 'busy' instead of piling up."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._next = 0.0

    async def wait(self, budget: float) -> None:
        interval = 1.0 / max(get_settings().name_lookup_max_per_second, 0.1)
        now = self._clock()
        slot = max(now, self._next)
        delay = slot - now
        if delay > budget:
            raise SourceError("MARS is already asking PubChem as often as it is allowed to; the molecule is not named for now", counts=False)
        self._next = slot + interval
        if delay > 0:
            await asyncio.sleep(delay)


breaker = Breaker()
throttle = Throttle()
# Tests replace this to answer without a network (httpx.MockTransport).
_transport: httpx.AsyncBaseTransport | None = None
_inflight: dict[str, asyncio.Future[Lookup]] = {}


def unavailable(key: str, reason: str) -> NameResponse:
    return NameResponse(status=NameStatus.UNAVAILABLE, inchikey=key, source=SOURCE, reason=reason)


def pick_synonyms(synonyms: list[str], taken: list[str | None], limit: int) -> list[str]:
    """The first `limit` synonyms in the source's own order, leaving out registry numbers and database ids and anything that only
    repeats a name already shown (compared without case)."""
    seen = {t.casefold() for t in taken if t}
    out: list[str] = []
    for raw in synonyms:
        s = raw.strip()
        if not s or _IDENTIFIER.match(s) or s.casefold() in seen:
            continue
        seen.add(s.casefold())
        out.append(s)
        if len(out) >= limit:
            break
    return out


async def _get(client: httpx.AsyncClient, url: str, budget: float) -> httpx.Response:
    """One request to the source, through the throttle and the breaker, with every failure turned into a `SourceError`."""
    if not breaker.allow():
        raise SourceError(
            f"{SOURCE} has not been answering, so MARS has paused asking it for {get_settings().name_breaker_open_seconds:g} s; the molecule is not named for now",
            counts=False,
        )
    try:
        await throttle.wait(budget)
    except SourceError:
        breaker.release()
        raise
    seconds = get_settings().name_lookup_timeout_seconds
    try:
        # httpx's timeout bounds each phase (connect, each read), not the whole request, so a source that drips bytes could hold
        # a lookup far longer; wait_for puts one ceiling on the lot.
        res = await asyncio.wait_for(client.get(url, timeout=seconds), timeout=seconds)
    except (httpx.TimeoutException, TimeoutError):
        breaker.failure()
        raise SourceError(f"{SOURCE} did not answer within {seconds:g} s; the molecule is not named for now") from None
    except httpx.HTTPError:
        breaker.failure()
        raise SourceError(f"{SOURCE} could not be reached; the molecule is not named for now") from None
    if res.status_code == 404:
        breaker.success()  # an answer: the source works and has no record
        return res
    if res.status_code != 200:
        breaker.failure()
        if res.status_code in (429, 503):
            raise SourceError(f"{SOURCE} is busy (HTTP {res.status_code}); the molecule is not named for now")
        raise SourceError(f"{SOURCE} answered with an error (HTTP {res.status_code}); the molecule is not named for now")
    breaker.success()
    return res


def _json(res: httpx.Response) -> dict:
    try:
        body = res.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        breaker.failure()
        raise SourceError(f"{SOURCE} answered in a form MARS did not understand; the molecule is not named for now")
    return body


async def lookup_pubchem(key: str) -> Lookup:
    """Ask PubChem about one InChIKey. Never raises for the source's failures: they come back as `unavailable`."""
    settings = get_settings()
    if not settings.name_lookup_enabled:
        return Lookup(unavailable(key, "Name lookup is switched off on this server; the molecule is not named"), cacheable=False)
    base = settings.name_lookup_base_url.rstrip("/")
    budget = settings.name_lookup_timeout_seconds
    try:
        async with httpx.AsyncClient(transport=_transport, headers={"User-Agent": _USER_AGENT}, follow_redirects=False) as client:
            res = await _get(client, f"{base}/compound/inchikey/{key}/property/Title,IUPACName/JSON", budget)
            if res.status_code == 404:
                return Lookup(NameResponse(status=NameStatus.NOT_FOUND, inchikey=key, source=SOURCE), cacheable=True)
            rows = _json(res).get("PropertyTable", {}).get("Properties")
            if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) and isinstance(r.get("CID"), int) for r in rows):
                breaker.failure()
                raise SourceError(f"{SOURCE} answered in a form MARS did not understand; the molecule is not named for now")
            # One structure can have several records (a neutral and a charged depiction of the same key). The lowest CID is the
            # oldest and the one PubChem links to first; the choice is deterministic and the record id is shown with the name.
            row = min(rows, key=lambda r: r["CID"])
            cid = row["CID"]
            title = row.get("Title") if isinstance(row.get("Title"), str) else None
            iupac = row.get("IUPACName") if isinstance(row.get("IUPACName"), str) else None
            synonyms: list[str] = []
            complete = True
            try:
                syn_res = await _get(client, f"{base}/compound/cid/{cid}/synonyms/JSON", budget)
                if syn_res.status_code == 200:
                    info = _json(syn_res).get("InformationList", {}).get("Information")
                    listed = info[0].get("Synonym", []) if isinstance(info, list) and info and isinstance(info[0], dict) else []
                    synonyms = pick_synonyms([s for s in listed if isinstance(s, str)], [title, iupac], settings.name_max_synonyms)
            except SourceError:
                complete = False  # the name stands; the synonyms are simply not shown, and the answer is not kept
            return Lookup(
                NameResponse(
                    status=NameStatus.FOUND,
                    inchikey=key,
                    source=SOURCE,
                    source_record=f"CID {cid}",
                    source_url=_RECORD_URL.format(cid=cid),
                    preferred_name=title,
                    iupac_name=iupac,
                    synonyms=synonyms,
                ),
                cacheable=complete,
            )
    except SourceError as exc:
        return Lookup(unavailable(key, exc.reason), cacheable=False)


async def lookup(key: str) -> Lookup:
    """`lookup_pubchem` with one shared flight per key: concurrent requests for the same key wait for one upstream lookup."""
    pending = _inflight.get(key)
    if pending is None:
        pending = asyncio.ensure_future(lookup_pubchem(key))
        _inflight[key] = pending
        pending.add_done_callback(lambda _f, k=key: _inflight.pop(k, None))
    return await asyncio.shield(pending)
