"""Reject duplicate paid cash studies across clock-only source manifests.

Only v9 uses this adapter. Older task implementations and their pinned hashes
remain untouched. Every manifest is verified before a clock-neutral comparison.
"""
from .operating_cash_policy_task_v2 import OperatingCashPolicyTaskServiceV2


class OperatingCashPolicyTaskServiceV3(OperatingCashPolicyTaskServiceV2):
    def _stable_source_identity(self, binding, seen=None):
        seen = set() if seen is None else seen
        path = binding.get("path") if isinstance(binding, dict) else None
        if not isinstance(path, str) or path in seen or len(seen) > 10:
            raise ValueError("CASH_POLICY_SOURCE_CHAIN_INVALID")
        seen.add(path)
        manifest = self._bound(binding)
        if "base_binding" not in manifest:
            # The terminal official acquisition receipt is immutable and
            # includes its original source hash, issuer and fetch time.
            return {"receipt": binding}
        required = ("schema_version", "symbol", "selection", "selected_from",
                    "implementation_sha256", "action")
        if any(key not in manifest for key in required) or manifest["action"] != "no_order":
            raise ValueError("CASH_POLICY_SOURCE_CHAIN_INVALID")
        return {key: manifest[key] for key in required} | {
            "base": self._stable_source_identity(manifest["base_binding"], seen)}

    def _prior_schema_failure(self, *, symbol, source_binding, config):
        if not self.base.exists():
            return False
        current = self._stable_source_identity(source_binding)
        children = list(self.base.iterdir())
        if len(children) > 100:
            raise ValueError("CASH_POLICY_TASK_DISCOVERY_LIMIT_EXCEEDED")
        for directory in children:
            if not directory.is_dir() or not (directory / "input.json").is_file():
                continue
            with self._lock(directory):
                old, state, _ = self._load(directory.name)
            if (old.get("symbol") == symbol
                    and old.get("config", {}).get("model_id") == config.get("model_id")
                    and old.get("config", {}).get("authorization_reference")
                    == config.get("authorization_reference")
                    and state.get("status") == "FAILED"
                    and state.get("error_code") in {"HORIZON_EXACT_FIELDS_REQUIRED",
                                                     "HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED"}
                    and self._stable_source_identity(old["source_binding"]) == current):
                return True
        return False

    def _prior_equivalent_research(self, *, symbol, years, context, config, mode):
        if not self.base.exists():
            return False
        current = self._stable_source_identity(context["source_binding"])
        children = list(self.base.iterdir())
        if len(children) > 100:
            raise ValueError("CASH_POLICY_TASK_DISCOVERY_LIMIT_EXCEEDED")
        for directory in children:
            if not directory.is_dir() or not (directory / "input.json").is_file():
                continue
            with self._lock(directory):
                old, state, _ = self._load(directory.name)
            if (old.get("symbol") == symbol and old.get("years") == years
                    and old.get("mode") == mode
                    and old.get("config", {}).get("model_id") == config.get("model_id")
                    and old.get("config", {}).get("authorization_reference")
                    == config.get("authorization_reference")
                    and (state.get("status") in {"QUEUED", "RUNNING", "SUCCEEDED"}
                         or state.get("provider_requests", 0) > 0)
                    and self._stable_source_identity(old["source_binding"]) == current):
                return True
        return False
