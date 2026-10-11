"""DEPRECATED_COMPATIBILITY_SHIM: shared registry lives in infrastructure."""
from ...infrastructure.evidence.trust_root_registry import (
    DEFAULT_TRUST_REGISTRY_PATH, TRUST_REGISTRY_VERSION, TrustRootNotPinnedError,
    is_pinned_trust_root, pinned_trust_root_fingerprints, require_pinned_trust_root,
    trust_registry_path, trust_root_fingerprint, _set_test_trust_registry,
    _use_test_trust_registry,
)
