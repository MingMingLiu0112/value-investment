"""DEPRECATED_COMPATIBILITY_SHIM: forward to operations authorization."""

from .operations.authorization.m6_authorization_artifacts import (
    verify_authorization_artifacts,
)

__all__ = ["verify_authorization_artifacts"]
