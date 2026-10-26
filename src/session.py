"""Open/close an LSEG session using the session-definition API.

Credentials come from env vars or secrets.env (see config.load_secrets) and are
passed straight to the library; they are never logged or printed.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from .config import MIN_SECONDS_BETWEEN_CALLS, load_secrets

log = logging.getLogger(__name__)

try:
    import lseg.data as ld
    LIB = "lseg-data"
except ImportError:  # fall back to the predecessor package with the same API
    import refinitiv.data as ld  # type: ignore[no-redef]
    LIB = "refinitiv-data"


class CredentialsMissing(RuntimeError):
    pass


def open_session(kind: str = "desktop"):
    """Open and set the default session. kind: 'desktop' or 'platform'."""
    secrets = load_secrets()
    if "LSEG_APP_KEY" not in secrets:
        raise CredentialsMissing("LSEG_APP_KEY is not set (env var or secrets.env).")

    if kind == "desktop":
        definition = ld.session.desktop.Definition(app_key=secrets["LSEG_APP_KEY"])
    elif kind == "platform":
        missing = [k for k in ("LSEG_USERNAME", "LSEG_PASSWORD") if k not in secrets]
        if missing:
            raise CredentialsMissing(f"Platform session needs {', '.join(missing)}.")
        grant = ld.session.platform.GrantPassword(
            username=secrets["LSEG_USERNAME"], password=secrets["LSEG_PASSWORD"]
        )
        definition = ld.session.platform.Definition(
            app_key=secrets["LSEG_APP_KEY"], grant=grant, signon_control=True
        )
    else:
        raise ValueError(f"Unknown session kind {kind!r}; use 'desktop' or 'platform'.")

    session = definition.get_session()
    ld.session.set_default(session)
    session.open()
    state = str(getattr(session, "open_state", ""))
    log.info("%s session via %s: state=%s", kind, LIB, state)
    if "Opened" not in state:
        raise RuntimeError(
            f"{kind} session did not open (state={state}). For desktop, make sure "
            "Workspace is running and signed in; for platform, check the credentials."
        )
    return session


def close_session(session) -> None:
    try:
        session.close()
        log.info("Session closed")
    except Exception as exc:  # closing should never mask the real error
        log.warning("Error closing session: %s", type(exc).__name__)


_last_call = [0.0]
_PERMANENT_ERRORS = ("invalid", "not found", "unable to resolve", "no data", "not entitled",
                     "unknown field", "not recognized", "permission")


def _is_transient(exc: BaseException) -> bool:
    """Retry network/rate-limit errors, not bad instruments or fields."""
    return not any(p in str(exc).lower() for p in _PERMANENT_ERRORS)


def call_api(fn, *args, attempts: int = 4, **kwargs):
    """Call an ld.* function with a global rate limit and exponential backoff."""
    from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

    for attempt in Retrying(stop=stop_after_attempt(attempts), retry=retry_if_exception(_is_transient),
                            wait=wait_exponential(multiplier=1, min=2, max=60), reraise=True):
        with attempt:
            gap = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call[0])
            if gap > 0:
                time.sleep(gap)
            _last_call[0] = time.monotonic()
            n = attempt.retry_state.attempt_number
            if n > 1:
                log.info("Retry %d/%d for %s", n, attempts, getattr(fn, "__name__", fn))
            return fn(*args, **kwargs)


@contextmanager
def lseg_session(kind: str = "desktop"):
    session = open_session(kind)
    try:
        yield session
    finally:
        close_session(session)
