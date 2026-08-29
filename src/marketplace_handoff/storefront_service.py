from fastapi import Depends, FastAPI, HTTPException
from openai import APIConnectionError, APIStatusError

from .handoff_service import (
    CompletionPort,
    OrderHandoffRequest,
    OrderHandoffResult,
    build_completion_client,
    prepare_handoff,
)

storefront = FastAPI(title="Marketplace order handoff")


@storefront.post("/orders/handoff", response_model=OrderHandoffResult)
def create_order_handoff(
    order: OrderHandoffRequest,
    completions: CompletionPort = Depends(build_completion_client),
) -> OrderHandoffResult:
    try:
        return prepare_handoff(order, completions)
    except APIStatusError as exc:
        detail = exc.body if isinstance(exc.body, dict) else {"message": str(exc)}
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=503, detail="AI gateway connection failed") from exc

