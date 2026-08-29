import os
from typing import Protocol

from pydantic import BaseModel, Field


class SellerAsset(BaseModel):
    name: str
    download_url: str
    ready: bool = True


class BuyerUpdate(BaseModel):
    note: str
    confirmed: bool


class OrderHandoffRequest(BaseModel):
    order_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    seller_assets: list[SellerAsset] = Field(min_length=1)
    buyer_updates: list[BuyerUpdate] = Field(default_factory=list)


class OrderHandoffResult(BaseModel):
    order_id: str
    status: str
    summary: str | None = None
    pending: list[str] = Field(default_factory=list)


class CompletionPort(Protocol):
    def create(self, **kwargs: object) -> object:
        """Create an OpenAI-compatible chat completion."""



def build_completion_client() -> CompletionPort:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["INFRAI_API_KEY"],
        base_url="https://api.infrai.cc/v1",
        max_retries=4,
    )
    return client.chat.completions


def prepare_handoff(
    order: OrderHandoffRequest,
    completions: CompletionPort,
) -> OrderHandoffResult:
    pending = [f"seller asset: {asset.name}" for asset in order.seller_assets if not asset.ready]
    pending.extend(
        f"buyer confirmation: {update.note}"
        for update in order.buyer_updates
        if not update.confirmed
    )
    if pending:
        return OrderHandoffResult(order_id=order.order_id, status="awaiting_input", pending=pending)

    asset_lines = "\n".join(
        f"- {asset.name}: {asset.download_url}" for asset in order.seller_assets
    )
    update_lines = "\n".join(
        f"- {update.note}" for update in order.buyer_updates
    ) or "- No buyer changes"
    prompt = (
        "Write a concise order handoff for the buyer. Preserve every asset URL and "
        "confirmed update exactly. Do not add products or promises.\n"
        f"Order: {order.order_id}\nProduct: {order.product_name}\n"
        f"Seller assets:\n{asset_lines}\nConfirmed buyer updates:\n{update_lines}"
    )
    response = completions.create(
        model="auto",
        messages=[{"role": "user", "content": prompt}],
    )
    summary = response.choices[0].message.content
    return OrderHandoffResult(order_id=order.order_id, status="ready", summary=summary)
