import time
import uuid
from typing import Any

from pydantic import ValidationError

from app.agent.registry import ToolContext, ToolResult, registry
from app.models import AgentToolCall


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
        if not set(tool.permissions).issubset(context.actor.scopes):
            result = ToolResult(ok=False, error="Permission denied", error_code="permission_denied")
            status = "permission_denied"
        elif tool.mutates:
            result = ToolResult(
                ok=False,
                error="This action requires explicit user confirmation",
                error_code="confirmation_required",
                meta={"preview": validated.model_dump(mode="json")},
            )
            status = "confirmation_required"
        else:
            try:
                result = await tool.handler(validated, context)
                status = "success" if result.ok else result.error_code or "error"
                error = result.error
            except Exception:
                result = ToolResult(ok=False, error="Tool execution failed", error_code="internal_error")
                status = "internal_error"
                error = "Tool execution failed"

    context.session.add(
        AgentToolCall(
            id=uuid.uuid4(),
            household_id=context.actor.household_id,
            actor_member_id=context.actor.member_id,
            agent="hermes",
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