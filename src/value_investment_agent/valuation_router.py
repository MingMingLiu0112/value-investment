"""Select and construct a valuation model from an explicit registry.

The router maps an economic profile to a registered model. The registry maps
model ids and model types to builders and required facts contracts. Neither
component may consult a security symbol.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .research_profile import PROFILES, ResearchProfile
from .valuation_models.cyclical import CyclicalFacts, CyclicalNormalizedValuationModel
from .valuation_models.fcff import FCFFValuationModel, FinancialFacts
from .valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeEquityValuationModel,
)


ROUTE_SUPPORTED = "SUPPORTED"
ROUTE_UNSUPPORTED = "UNSUPPORTED"
ROUTE_MODEL_NOT_APPLICABLE = "MODEL_NOT_APPLICABLE"


@dataclass(frozen=True)
class ValuationModelRegistration:
    model_id: str
    model_type: str
    model_factory: type[Any]
    facts_contract: type[Any]
    required_inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.model_type.strip():
            raise ValueError("Valuation model registration requires id and type")
        if not self.required_inputs:
            raise ValueError("Valuation model registration requires input contract")
        object.__setattr__(self, "required_inputs", tuple(self.required_inputs))

    def build(self) -> Any:
        instance = self.model_factory()
        registered_type = getattr(instance, "model_type", self.model_type)
        if registered_type != self.model_type:
            raise ValueError(
                f"Registered model {self.model_id} built type {registered_type}"
            )
        return instance


class ValuationModelRegistry:
    """Immutable lookup for model type, builder and required input contract."""

    def __init__(
        self,
        registrations: Iterable[ValuationModelRegistration] = (),
    ) -> None:
        self._by_id: dict[str, ValuationModelRegistration] = {}
        self._by_type: dict[str, ValuationModelRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(
        self,
        registration: ValuationModelRegistration,
    ) -> None:
        if not isinstance(registration, ValuationModelRegistration):
            raise TypeError("Model registry only accepts typed registrations")
        if registration.model_id in self._by_id:
            raise ValueError(f"Duplicate model id: {registration.model_id}")
        if registration.model_type in self._by_type:
            raise ValueError(f"Duplicate model type: {registration.model_type}")
        self._by_id[registration.model_id] = registration
        self._by_type[registration.model_type] = registration

    def get(self, model_id: str) -> ValuationModelRegistration | None:
        return self._by_id.get(model_id)

    def by_model_type(self, model_type: str) -> ValuationModelRegistration | None:
        return self._by_type.get(model_type)

    def build(self, model_id: str) -> Any:
        registration = self.get(model_id)
        if registration is None:
            raise ValueError(f"Unknown valuation model id: {model_id}")
        return registration.build()

    def required_inputs(self, model_id: str) -> tuple[str, ...]:
        registration = self.get(model_id)
        if registration is None:
            raise ValueError(f"Unknown valuation model id: {model_id}")
        return registration.required_inputs

    def allowed_models(self, profile: ResearchProfile) -> tuple[str, ...]:
        if not isinstance(profile, ResearchProfile):
            raise ValueError("Allowed models require an explicit ResearchProfile")
        return tuple(
            dict.fromkeys(
                model_id
                for model_id in (
                    profile.primary_valuation_model,
                    *profile.cross_check_models,
                )
                if model_id not in profile.unsupported_models
            )
        )

    def registrations(self) -> Mapping[str, ValuationModelRegistration]:
        return dict(self._by_id)


_DEFAULT_REGISTRATIONS = (
        ValuationModelRegistration(
            "fcff",
            "FCFF",
            FCFFValuationModel,
            FinancialFacts,
            (*FinancialFacts.REQUIRED_FCFF_INPUTS, "scenario_inputs"),
        ),
        ValuationModelRegistration(
            "cyclical_normalized",
            "cyclical_normalized",
            CyclicalNormalizedValuationModel,
            CyclicalFacts,
            CyclicalFacts.REQUIRED_CYCLICAL_INPUTS,
        ),
        ValuationModelRegistration(
            "residual_income_or_equity_value",
            "residual_income_or_equity_value",
            ResidualIncomeEquityValuationModel,
            QualityCompounderFacts,
            (*QualityCompounderFacts.REQUIRED_COMMON_INPUTS, "scenario_inputs"),
        ),
)
VALUATION_MODEL_REGISTRY = ValuationModelRegistry(_DEFAULT_REGISTRATIONS)

# Backward-compatible read-only alias for callers that only need model_id lookup.
MODEL_REGISTRY = VALUATION_MODEL_REGISTRY.registrations()


@dataclass(frozen=True)
class ValuationRoute:
    profile_id: str
    requested_model: str | None
    selected_model: str
    status: str
    model_type: str | None
    model_factory: type[Any] | None
    facts_contract: type[Any] | None
    blockers: list[str]
    required_inputs: tuple[str, ...] = ()

    def as_policy(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "requested_model": self.requested_model,
            "selected_model": self.selected_model,
            "status": self.status,
            "model_type": self.model_type,
            "model_factory": self.model_factory.__name__ if self.model_factory else None,
            "facts_contract": self.facts_contract.__name__ if self.facts_contract else None,
            "required_inputs": list(self.required_inputs),
            "blockers": list(self.blockers),
        }

    def build_model(self) -> Any:
        if self.status != ROUTE_SUPPORTED:
            raise ValueError("An unsupported valuation route cannot build a model")
        if self.model_factory is None:
            raise ValueError("A supported valuation route requires a model factory")
        instance = self.model_factory()
        if getattr(instance, "model_type", self.model_type) != self.model_type:
            raise ValueError("Valuation route built an unexpected model type")
        return instance


class ValuationRouter:
    """Map an explicit economic profile to a registered valuation model."""

    def __init__(
        self,
        registry: ValuationModelRegistry | None = None,
    ) -> None:
        self.registry = registry or VALUATION_MODEL_REGISTRY

    def route(
        self,
        profile: ResearchProfile,
        requested_model: str | None = None,
    ) -> ValuationRoute:
        if not isinstance(profile, ResearchProfile):
            raise ValueError("Valuation routing requires an explicit ResearchProfile")

        primary_model = profile.primary_valuation_model
        selected_model = requested_model or primary_model
        blockers: list[str] = []

        authorized_models = {primary_model, *profile.cross_check_models}
        rejected_models = set(profile.unsupported_models)
        if selected_model not in authorized_models | rejected_models:
            blockers.append(f"model_not_authorized_for_profile:{selected_model}")
            return ValuationRoute(
                profile.profile_id, requested_model, selected_model, ROUTE_UNSUPPORTED,
                None, None, None, blockers, (),
            )

        if selected_model != primary_model:
            blockers.append(
                f"model_not_primary_for_profile:{selected_model}:{primary_model}"
            )
            return ValuationRoute(
                profile.profile_id, requested_model, selected_model,
                ROUTE_MODEL_NOT_APPLICABLE, None, None, None, blockers, (),
            )

        registration = self.registry.get(primary_model)
        if registration is None:
            blockers.append(f"generic_engine_not_registered:{primary_model}")
            return ValuationRoute(
                profile.profile_id, requested_model, selected_model, ROUTE_UNSUPPORTED,
                None, None, None, blockers, (),
            )

        return ValuationRoute(
            profile.profile_id,
            requested_model,
            selected_model,
            ROUTE_SUPPORTED,
            registration.model_type,
            registration.model_factory,
            registration.facts_contract,
            [],
            registration.required_inputs,
        )


def route_profile(profile_id: str, requested_model: str | None = None) -> ValuationRoute:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown research profile: {profile_id}")
    return ValuationRouter().route(PROFILES[profile_id], requested_model)
