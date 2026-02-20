"""P2P communication module for OpenClaw."""

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
    __all__ = [
        'NoiseProtocol',
        'NoisePattern',
        'SessionState',
        'HandshakeError',
        'IdentityVerificationError',
        'SessionNotEstablishedError',
        'DecryptionError',
        'ReplayAttackError',
        'MessageOrderError'
    ]
except ImportError:
    # noise_protocol not yet implemented
    __all__ = []
