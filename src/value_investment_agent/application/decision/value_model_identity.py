"""Resolve a retained type/version through the executing registered catalog."""
import hashlib
import importlib
import inspect
from pathlib import Path

from ...research_profile import PROFILES
from ...valuation_router import VALUATION_MODEL_REGISTRY, ValuationRouter, ROUTE_SUPPORTED


def resolve_value_model_identity(valuation, *, profile_id):
    """Catalog identity is not model validity, G3 or economic approval.

    Versions come from the registered implementation's own declarations. No
    symbol mapping, string reconstruction or valuation calculation is performed.
    """
    registration = VALUATION_MODEL_REGISTRY.by_model_type(valuation.get("model_type", ""))
    profile = PROFILES.get(profile_id)
    if registration is None or profile is None:
        return None
    route = ValuationRouter().route(profile, registration.model_id)
    if route.status != ROUTE_SUPPORTED:
        return None
    module = importlib.import_module(registration.model_factory.__module__)
    versions = {getattr(module, name, None) for name in ("MODEL_VERSION", "DATED_MODEL_VERSION")}
    versions.update(getattr(module, 'SUPPORTED_MODEL_VERSIONS', ()))
    version = valuation.get("model_version")
    if not version or version not in versions:
        return None
    if registration.build().model_type != valuation["model_type"]:
        return None
    registry_module = importlib.import_module(VALUATION_MODEL_REGISTRY.__class__.__module__)
    evidence = []
    source_root = Path(__file__).resolve().parents[4]
    for source in (registry_module, module):
        path = Path(inspect.getfile(source)).resolve()
        evidence.append(dict(module=source.__name__, path=path.relative_to(source_root).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return dict(model_id=registration.model_id, model_type=registration.model_type,
        model_version=version, profile_id=profile_id,
        scope="REGISTERED_IMPLEMENTATION_IDENTITY_NOT_MODEL_APPROVAL", code_evidence=evidence)


def project_catalog_identity(explanation):
    """Only fill absent public identity; never replace a restored decision id."""
    if explanation.get("model_id") or (explanation.get("model_validity") or {}).get("model_id"):
        return explanation
    profile_id = ((explanation.get("price_context") or {}).get("price_attractiveness") or {}).get("profile_id")
    identity = resolve_value_model_identity(explanation.get("valuation") or {}, profile_id=profile_id)
    if identity is None:
        return explanation
    return {**explanation, "model_id": identity["model_id"], "model_identity_evidence": identity}
