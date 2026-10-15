"""Root registers these routes with its existing local session and actor resolver."""
from datetime import datetime, timezone

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.decision.value_policy_interaction import (
    PolicyAccessDenied, PolicyConflict, require_policy_authority,
)
from .local_auth import (
    AUTHORIZATION_REQUIRED, LocalAuthorizationError, authorize,
)


def register_value_policy_routes(api: FastAPI, *, sessions, principal_resolver,
                                 service=None, get_service=None,
                                 port=8001, clock=lambda: datetime.now(timezone.utc)):
    """Resolver(Request)->PolicyPrincipal is trusted config, not request claims.

    No unlock endpoint, real registry pointer, G3 approval or production write.
    """
    if (service is None) == (get_service is None):
        raise ValueError("Supply exactly one service or get_service factory")
    factory = get_service if get_service is not None else lambda: service

    def dispatch(request, operation):
        try:
            authorize(request, session=sessions, port=port)
            principal = principal_resolver(request)
            require_policy_authority(principal)
            body = operation(principal, factory())
            return JSONResponse(body, headers={"Cache-Control": "no-store"})
        except LocalAuthorizationError as error:
            code = 401 if error.code == AUTHORIZATION_REQUIRED else 403
            body = dict(action="no_order", status=error.code, detail=error.detail)
        except PolicyAccessDenied as error:
            code, body = 403, dict(action="no_order", status="VALUE_POLICY_FORBIDDEN", detail=str(error))
        except PolicyConflict as error:
            code, body = 409, dict(action="no_order", status="VALUE_POLICY_CONFLICT", detail=str(error))
        except (ValueError, KeyError, TypeError, ArithmeticError):
            code, body = 422, dict(action="no_order", status="VALUE_POLICY_INVALID",
                                  detail="政策输入或研究绑定无效，请核对后重新预览")
        except OSError:
            code, body = 503, dict(action="no_order", status="VALUE_POLICY_UNAVAILABLE",
                                  detail="政策资料暂不可用，请重试；确认结果可安全重复查询")
        return JSONResponse(body, status_code=code, headers={"Cache-Control": "no-store"})

    @api.post("/api/v1/value-policy-review/{symbol}/preview")
    def preview(symbol: str, request: Request, payload: dict = Body(...)):
        return dispatch(request, lambda p, svc: svc.preview(symbol, payload, principal=p, now=clock()))

    @api.get("/api/v1/value-policy-review/{symbol}/status")
    def status(symbol: str, request: Request):
        return dispatch(request, lambda p, svc: svc.status(symbol, principal=p, now=clock()))

    @api.get("/api/v1/value-policy-review/{symbol}/handoff")
    def handoff(symbol: str, request: Request):
        return dispatch(request, lambda p, svc: svc.review_handoff(symbol, principal=p, now=clock()))

    @api.post("/api/v1/value-policy-review/{symbol}/confirm")
    def confirm(symbol: str, request: Request, payload: dict = Body(...)):
        def run(principal, svc):
            if set(payload) != {"preview_id", "acknowledged", "note"}:
                raise ValueError("Unexpected confirmation fields")
            envelope = svc._read(payload["preview_id"])
            if envelope["prepared"]["draft"]["basis"]["symbol"] != symbol:
                raise ValueError("Confirmation security mismatch")
            return svc.confirm(payload["preview_id"],
                {key: payload[key] for key in ("acknowledged", "note")}, principal=principal, now=clock())
        return dispatch(request, run)
