"""Additive module-run dispatch outside provenance-frozen financial codecs."""
from ..domain.research.module_run_v1 import ModuleRun, ModuleRunCodec
from ..research_artifact_codecs import artifact_payload as legacy_payload, decode_artifact as legacy_decode


def artifact_payload(value):
    if isinstance(value, ModuleRun):
        return "module_run", ModuleRunCodec.to_payload(value)
    return legacy_payload(value)


def decode_artifact(artifact_type, payload, **kwargs):
    if artifact_type == "module_run":
        return ModuleRunCodec.from_payload(payload, **kwargs)
    return legacy_decode(artifact_type, payload, **kwargs)
