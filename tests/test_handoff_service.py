from types import SimpleNamespace

from marketplace_handoff.handoff_service import OrderHandoffRequest, prepare_handoff


class RecordingCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        message = SimpleNamespace(content="Download the approved storefront kit from the supplied link.")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_unconfirmed_buyer_update_holds_order_without_ai_call() -> None:
    completions = RecordingCompletions()
    order = OrderHandoffRequest.model_validate(
        {
            "order_id": "ORDER-77",
            "product_name": "Checkout theme",
            "seller_assets": [
                {"name": "Theme archive", "download_url": "https://downloads.example/theme.zip"}
            ],
            "buyer_updates": [{"note": "Change the cart button label", "confirmed": False}],
        }
    )

    result = prepare_handoff(order, completions)

    assert result.status == "awaiting_input"
    assert result.pending == ["buyer confirmation: Change the cart button label"]
    assert completions.calls == []


def test_ready_order_uses_auto_model_and_includes_assets() -> None:
    completions = RecordingCompletions()
    order = OrderHandoffRequest.model_validate(
        {
            "order_id": "ORDER-78",
            "product_name": "Checkout theme",
            "seller_assets": [
                {"name": "Theme archive", "download_url": "https://downloads.example/theme.zip"}
            ],
            "buyer_updates": [{"note": "Keep the approved cart copy", "confirmed": True}],
        }
    )

    result = prepare_handoff(order, completions)

    assert result.status == "ready"
    assert completions.calls[0]["model"] == "auto"
    assert "https://downloads.example/theme.zip" in completions.calls[0]["messages"][0]["content"]

