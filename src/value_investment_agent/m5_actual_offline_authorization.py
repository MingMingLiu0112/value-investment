"""DEPRECATED_COMPATIBILITY_SHIM: forward to the M5 approval boundary."""

from .operations.authorization.m5_actual_approval_receipt import (
    ARTIFACT_NAMES,
    AUTHORIZATION_SCHEMA_VERSION,
    BUNDLE_VERSION,
    M5ActualOfflineAuthorization,
    RECEIPT_VERSION,
    SUBJECT_FIELDS,
    TRUST_ROOT_VERSION,
    USER_CONFIRMED_DELEGATED_REVIEW,
    actual_offline_authorization_from_payload,
    build_subject,
    event_identity_sha256,
    graph_sha256,
    require_actual_offline_authorization,
    verify_m5_actual_approval_receipt,
)

__all__ = [
    "ARTIFACT_NAMES",
    "AUTHORIZATION_SCHEMA_VERSION",
    "BUNDLE_VERSION",
    "M5ActualOfflineAuthorization",
    "RECEIPT_VERSION",
    "SUBJECT_FIELDS",
    "TRUST_ROOT_VERSION",
    "USER_CONFIRMED_DELEGATED_REVIEW",
    "actual_offline_authorization_from_payload",
    "build_subject",
    "event_identity_sha256",
    "graph_sha256",
    "require_actual_offline_authorization",
    "verify_m5_actual_approval_receipt",
]
