"""P2P communication module for OpenClaw."""

# Import noise_protocol if available
try:
    from .noise_protocol import (
        NoiseProtocol,
        NoisePattern,
        SessionState,
        HandshakeError,
        IdentityVerificationError,
        SessionNotEstablishedError,
        DecryptionError,
        ReplayAttackError,
        MessageOrderError
    )
    _noise_available = True
except ImportError:
    _noise_available = False

__all__ = []

if _noise_available:
    __all__.extend([
        'NoiseProtocol',
        'NoisePattern',
        'SessionState',
        'HandshakeError',
        'IdentityVerificationError',
        'SessionNotEstablishedError',
        'DecryptionError',
        'ReplayAttackError',
        'MessageOrderError'
    ])
