"""Outbound request signers.

The article signs each gateway call with ``MD5(appid + secret + ts)``
— cheap, easy to debug, "enough internal-network strength". This
module exposes that recipe as :class:`MD5AppSecretSigner` and a
:class:`NoopSigner` for callers that do not need signed traffic.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Protocol


class Signer(Protocol):
    """Compute a signature header value for a serialised payload."""

    def sign(self, payload: bytes) -> str:
        ...


class NoopSigner:
    """Returns an empty signature — no extra bytes on the wire."""

    def sign(self, payload: bytes) -> str:
        return ""


class MD5AppSecretSigner:
    """Article-faithful ``MD5(appid + secret + ts + payload)`` signer.

    The app id, shared secret and timestamp are concatenated with the
    request body, hashed with MD5, and returned as the signature. The
    timestamp is included as the millisecond epoch so two requests
    issued in the same millisecond still collide intentionally.
    """

    def __init__(self, app_id: str, secret: str) -> None:
        self.app_id = app_id
        self.secret = secret

    def sign(self, payload: bytes) -> str:
        ts = str(int(time.time() * 1000))
        seed = f"{self.app_id}{self.secret}{ts}".encode("utf-8") + payload
        return hashlib.md5(seed).hexdigest()


class HMACSHA256Signer:
    """A more modern alternative — HMAC-SHA256 over (payload + ts)."""

    def __init__(self, secret: str) -> None:
        self.secret = secret.encode("utf-8")

    def sign(self, payload: bytes) -> str:
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
