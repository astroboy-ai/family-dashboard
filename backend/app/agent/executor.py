import time
import uuid
from typing import Any

import structlog
from pydantic import ValidationError

from app.agent.registry import ToolContext, ToolResult, registry
from app.models import AgentToolCall

logger = structlog.get_logger(__name__)


async def execute_tool(
    *,
    name: str,
    params: dict[str, Any],
    context: ToolContext,
) -> ToolResult:
    tool = registry.get(name)
    if tool is None:
        return ToolResult(ok=False, error="Tool not found", error_code="not_found")

    started_at = time.perf_counter()
    status = "success"
    error: str | None = None
    try:
        validated = tool.params_model.model_validate(params)
    except ValidationError:
        result = ToolResult(ok=False, error="Invalid tool parameters", error_code="invalid_params")
        status = "invalid_params"
    else:
        # Scopes are the consent mechanism for writes. A mutating tool requires
        # an explicit write scope on the token; minting the token with that
        # scope is the operator's approval, so there is no per-call prompt.
        # ``tool.mutates`` marks a tool as write-capable, it does not itself
        # block one — the scope check below is what actually gates it.
        required = set(tool.permissions)
        if tool.mutates and not any(scope.endswith(".write") for scope in required):
            # A write tool with no write scope is a wiring mistake: it would be
            # gated by nothing but the read scope it happens to declare.
            logger.error("mutating_tool_without_write_scope", tool=name)
            result = ToolResult(
                ok=False,
                error="Tool is misconfigured",
                error_code="internal_error",
            )
            status = "internal_error"
            error = "mutating tool declares no write scope"
        elif not required.issubset(context.actor.scopes):
            result = ToolResult(ok=False, error="Permission denied", error_code="permission_denied")
            status = "permission_denied"
        else:
            try:
                result = await tool.handler(validated, context)
                status = "success" if result.ok else result.error_code or "error"
                error = result.error
            except Exception:
                logger.exception("tool_execution_failed", tool=name)
                result = ToolResult(ok=False, error="Tool execution failed", error_code="internal_error")
                status = "internal_error"
                error = "Tool execution failed"

    context.session.add(
        AgentToolCall(
            id=uuid.uuid4(),
            household_id=context.actor.household_id,
            actor_member_id=context.actor.member_id,
            agent=context.agent,
            tool_name=name,
            params=_redact_params(params),
            result_summary=result.error_code or ("ok" if result.ok else "error"),
            status=status,
            error=error,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
    )
    await context.session.commit()
    return result


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    secret_keys = {"password", "pin", "token", "secret", "authorization"}
    return {
        key: "[redacted]" if key.casefold() in secret_keys else value
        for key, value in params.items()
    }