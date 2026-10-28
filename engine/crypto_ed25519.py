"""
RenderFlow — RFC 8032 Ed25519 Cryptographic Signature Verification
===================================================================
Pure-Python, zero-dependency implementation of Ed25519 digital signatures.
Used by the auto-updater to cryptographically authenticate release manifests
and prevent tampering, spoofing, or untrusted payload execution.
"""

import hashlib
from typing import Tuple, Optional

# Curve parameters (RFC 8032)
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, -1, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)

# RenderFlow Master Release Public Key (Hex)
# Corresponding private key is held strictly by the release maintainer and is never bundled.
RENDERFLOW_MASTER_PUBLIC_KEY = "661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e"

def _inv(z: int) -> int:
    return pow(z, _Q - 2, _Q)

def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x

_By = 4 * _inv(5) % _Q
_Bx = _xrecover(_By)
_B = (_Bx, _By)

def _edwards_add(P: Tuple[int, int], Q: Tuple[int, int]) -> Tuple[int, int]:
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _D * x1 * x2 * y1 * y2) % _Q
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _D * x1 * x2 * y1 * y2) % _Q
    return (x3, y3)

def _scalarmult(P: Tuple[int, int], e: int) -> Tuple[int, int]:
    if e == 0:
        return (0, 1)
    Q = _scalarmult(P, e // 2)
    Q = _edwards_add(Q, Q)
    if e & 1:
        Q = _edwards_add(Q, P)
    return Q

def _encodeint(y: int) -> bytes:
    return int.to_bytes(y, 32, "little")

def _decodeint(b: bytes) -> int:
    return int.from_bytes(b, "little")

def _encodepoint(P: Tuple[int, int]) -> bytes:
    x, y = P
    b = bytearray(_encodeint(y))
    if x & 1:
        b[31] |= 0x80
    return bytes(b)

def _decodepoint(b: bytes) -> Tuple[int, int]:
    y = _decodeint(b) & ((1 << 255) - 1)
    x = _xrecover(y)
    if (x & 1) != (b[31] >> 7):
        x = _Q - x
    return (x, y)

def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()

def public_key_from_secret(secret_key_bytes: bytes) -> bytes:
    """Derive 32-byte public key from 32-byte secret key."""
    if len(secret_key_bytes) != 32:
        raise ValueError("Secret key must be exactly 32 bytes.")
    h = _H(secret_key_bytes)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 64
    A = _scalarmult(_B, a)
    return _encodepoint(A)

def sign_message(message: bytes, secret_key_bytes: bytes, public_key_bytes: Optional[bytes] = None) -> bytes:
    """Produce 64-byte Ed25519 signature over message bytes."""
    if public_key_bytes is None:
        public_key_bytes = public_key_from_secret(secret_key_bytes)
    h = _H(secret_key_bytes)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 64
    r = int.from_bytes(_H(h[32:] + message), "little") % _L
    R = _scalarmult(_B, r)
    R_bytes = _encodepoint(R)
    k = int.from_bytes(_H(R_bytes + public_key_bytes + message), "little") % _L
    S = (r + k * a) % _L
    return R_bytes + _encodeint(S)

def verify_signature(message: bytes, signature_bytes: bytes, public_key_bytes: Optional[bytes] = None) -> bool:
    """
    Verify Ed25519 signature. Returns True if valid, False otherwise.
    If public_key_bytes is omitted, verifies against RENDERFLOW_MASTER_PUBLIC_KEY.
    """
    try:
        if public_key_bytes is None:
            public_key_bytes = bytes.fromhex(RENDERFLOW_MASTER_PUBLIC_KEY)
        if len(signature_bytes) != 64 or len(public_key_bytes) != 32:
            return False
        R_bytes = signature_bytes[:32]
        S = _decodeint(signature_bytes[32:])
        if S >= _L:
            return False
        A = _decodepoint(public_key_bytes)
        R = _decodepoint(R_bytes)
        k = int.from_bytes(_H(R_bytes + public_key_bytes + message), "little") % _L
        SB = _scalarmult(_B, S)
        kA = _scalarmult(A, k)
        return SB == _edwards_add(R, kA)
    except Exception:
        return False

# Convenience aliases
ed25519_sign = sign_message
ed25519_verify = verify_signature
ed25519_sk_to_pk = public_key_from_secret

