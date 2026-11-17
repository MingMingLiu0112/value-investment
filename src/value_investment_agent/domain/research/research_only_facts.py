"""Unadmitted source observations when no valuation model has been assigned."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import re

RESEARCH_ONLY_MODE = 'research_only_v1'
UNASSIGNED_PROFILE = 'unassigned_research'
NO_MODEL = 'unassigned'
NO_MODEL_VERSION = 'research-only-no-valuation-v1'
SOURCE_SCHEMA = 'source-bound-research-only-inputs-v1'


@dataclass(frozen=True)
class ResearchOnlyFacts:
    symbol: str
    as_of: date
    observations_json: str
    evidence_json: str
    blockers: tuple[str, ...]
    verified: bool = False
    confidence: str = 'LOW'
    scenario_inputs: None = None

    def __post_init__(self):
        if (not re.fullmatch(r'[0-9]{6}', self.symbol)
                or not isinstance(self.as_of, date) or isinstance(self.as_of, datetime)):
            raise ValueError('Research-only facts require security and financial period')
        if self.verified is not False or self.confidence != 'LOW' or self.scenario_inputs is not None:
            raise ValueError('Research-only observations cannot confer assurance or scenarios')
        observations, evidence = json.loads(self.observations_json), json.loads(self.evidence_json)
        if not isinstance(observations, list) or not isinstance(evidence, list):
            raise ValueError('Research-only observations/evidence must be lists')
        ids = [item.get('id') for item in evidence if isinstance(item, dict)]
        if len(ids) != len(evidence) or not all(ids) or len(set(ids)) != len(ids):
            raise ValueError('Research-only evidence requires unique ids')
        for row in observations:
            if (not isinstance(row, dict) or not row.get('field_name')
                    or not isinstance(row.get('evidence_refs'), list) or not row['evidence_refs']):
                raise ValueError('Research-only observation requires field and evidence references')
            if not set(row['evidence_refs']).issubset(ids):
                raise ValueError('Research-only observation references unbound evidence')
            value = row.get('value')
            if value is not None and (not isinstance(value, str) or not Decimal(value).is_finite()):
                raise ValueError('Research-only observation value must be a finite string or null')
        if not self.blockers or any(not isinstance(item, str) or not item.strip() for item in self.blockers):
            raise ValueError('Research-only facts require explicit applicability blockers')
        object.__setattr__(self, 'blockers', tuple(self.blockers))

    @property
    def observations(self):
        return tuple(json.loads(self.observations_json))

    @property
    def evidence_refs(self):
        return tuple(json.loads(self.evidence_json))

    def as_policy(self):
        return dict(facts_type='research_only', symbol=self.symbol, as_of=self.as_of.isoformat(),
            observations=list(self.observations), evidence_refs=list(self.evidence_refs),
            blockers=list(self.blockers), verified=False, confidence='LOW', scenario_inputs=None)

    @classmethod
    def from_payload(cls, payload):
        allowed = {'facts_type', 'symbol', 'as_of', 'observations', 'evidence_refs', 'blockers',
                   'verified', 'confidence', 'scenario_inputs'}
        if (set(payload) != allowed or payload['facts_type'] != 'research_only'
                or payload['verified'] is not False or payload['confidence'] != 'LOW'
                or payload['scenario_inputs'] is not None):
            raise ValueError('Exact unadmitted research-only facts contract required')
        return cls(payload['symbol'], date.fromisoformat(payload['as_of']),
            json.dumps(payload['observations'], allow_nan=False, sort_keys=True),
            json.dumps(payload['evidence_refs'], allow_nan=False, sort_keys=True),
            tuple(payload['blockers']))


def validate_research_only_scope(profile_id, requested_model, facts, forbidden):
    if profile_id != UNASSIGNED_PROFILE or requested_model is not None or not isinstance(facts, ResearchOnlyFacts):
        raise ValueError('Explicit research-only mode requires unassigned profile, typed observations and no model')
    if any(value is not None and value != () for value in forbidden):
        raise ValueError('Research-only mode forbids valuation, market, approval and personal decision inputs')
