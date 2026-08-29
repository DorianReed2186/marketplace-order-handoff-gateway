from marketplace_handoff.handoff_service import (
    BuyerUpdate,
    OrderHandoffRequest,
    SellerAsset,
    build_completion_client,
    prepare_handoff,
)


order = OrderHandoffRequest(
    order_id="ORDER-1042",
    product_name="Summer campaign storefront kit",
    seller_assets=[
        SellerAsset(name="Theme archive", download_url="https://downloads.example/theme.zip"),
        SellerAsset(name="Product photography", download_url="https://downloads.example/photos.zip"),
    ],
    buyer_updates=[BuyerUpdate(note="Use the approved green checkout button", confirmed=True)],
)

result = prepare_handoff(order, build_completion_client())
print(result.model_dump_json(indent=2))

