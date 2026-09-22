"""Select a valuation model from an economic profile, never from a symbol."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


MODEL_REGISTRY = {
    registration.model_id: registration
    for registration in (
        ValuationModelRegistration("fcff", "FCFF", FCFFValuationModel, FinancialFacts),
        ValuationModelRegistration(
            "cyclical_normalized",
            "cyclical_normalized",
            CyclicalNormalizedValuationModel,
            CyclicalFacts,
        ),
        ValuationModelRegistration(
            "residual_income_or_equity_value",
            "residual_income_or_equity_value",
            ResidualIncomeEquityValuationModel,
            QualityCompounderFacts,
        ),
    )
}


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

    def as_policy(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "requested_model": self.requested_model,
            "selected_model": self.selected_model,
            "status": self.status,
            "model_type": self.model_type,
            "model_factory": self.model_factory.__name__ if self.model_factory else None,
            "facts_contract": self.facts_contract.__name__ if self.facts_contract else None,
            "blockers": list(self.blockers),
        }


class ValuationRouter:
    """Map an explicit economic profile to a registered valuation model."""

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
                None, None, None, blockers,
            )

        if selected_model != primary_model:
            blockers.append(
                f"model_not_primary_for_profile:{selected_model}:{primary_model}"
            )
            return ValuationRoute(
                profile.profile_id, requested_model, selected_model,
                ROUTE_MODEL_NOT_APPLICABLE, None, None, None, blockers,
            )

        registration = MODEL_REGISTRY.get(primary_model)
        if registration is None:
            blockers.append(f"generic_engine_not_registered:{primary_model}")
            return ValuationRoute(
                profile.profile_id, requested_model, selected_model, ROUTE_UNSUPPORTED,
                None, None, None, blockers,
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
        )


def route_profile(profile_id: str, requested_model: str | None = None) -> ValuationRoute:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown research profile: {profile_id}")
    return ValuationRouter().route(PROFILES[profile_id], requested_model)
