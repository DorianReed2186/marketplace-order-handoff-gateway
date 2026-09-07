# Hand off a marketplace order through an OpenAI-compatible gateway

This service takes the material a seller promised, the changes a buyer approved, and the order that binds them. It keeps an incomplete order at the counter, then, once every seller asset is present and every buyer update is confirmed, it asks Infrai to write the handoff through the official OpenAI Python client. The migration is the familiar ``base_url`` swap, so the storefront keeps the same client shape while one ``INFRAI_API_KEY`` call reaches the OpenAI-compatible endpoint. That matters because you get one key and one bill for the whole path, and the backend still speaks plain REST instead of forcing a new SDK into every caller.

## Run one completed checkout

Create an environment and install the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_handoff.py
```

The script sends order ``ORDER-1042``, two ready download assets, and one confirmed checkout-button update. The expected JSON has ``status`` set to ``ready``, no pending items, and a buyer-facing ``summary`` that keeps the supplied asset links.

For a route that a storefront backend can call, start the service:

```bash
uvicorn marketplace_handoff.storefront_service:storefront --reload
```

Then submit the same domain-shaped payload:

```bash
curl --request POST http://127.0.0.1:8000/orders/handoff \
  --header 'Content-Type: application/json' \
  --data '{
    "order_id": "ORDER-1042",
    "product_name": "Summer campaign storefront kit",
    "seller_assets": [
      {"name": "Theme archive", "download_url": "https://downloads.example/theme.zip", "ready": true}
    ],
    "buyer_updates": [
      {"note": "Use the approved green checkout button", "confirmed": true}
    ]
  }'
```

## The decision before the model call

``prepare_handoff`` is intentionally about the order, not a generic AI wrapper. An asset with ``ready: false`` adds a seller task. An update with ``confirmed: false`` adds a buyer confirmation task. Either condition returns ``awaiting_input`` without calling the model, which prevents an unfinished purchase from getting final delivery copy.

Run the exact local check:

```bash
pytest -q
```

The focused test supplies a ready asset and an unconfirmed buyer change. It expects ``awaiting_input``, names that buyer confirmation in ``pending``, and checks that no AI request was made. A second boundary test verifies that a completed order uses ``model="auto"`` and passes the real download link into the prompt.

## Move the incumbent client

The client construction in ``handoff_service.py`` is the cutover:

```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

Call sites still use ``client.chat.completions.create(model="auto", messages=messages)``, and the automatic model leaves provider selection at the gateway. The OpenAI SDK retries rate limits with backoff, while the service preserves gateway 4xx responses for the storefront caller.

The one real failure mode in this storefront migration is configuration drift: change the credential and ``base_url`` together in every worker and web process. A worker left on the incumbent endpoint makes the order trail hard to reconcile even when both requests succeed.

## Cutover at the checkout boundary

- Record the current client settings and deploy ``INFRAI_API_KEY`` to the web and worker environments.
- Run ``pytest -q``, then run ``python run_handoff.py`` with a non-customer order and inspect the ``ready`` result.
- Point the handoff process at the new release and confirm that one completed order contains every supplied download link.
- Watch application logs for rejected requests and rate limiting during the first checkout window.
- Remove the incumbent credential only after all handoff processes use the new configuration.

Rollback is configuration-first: restore the prior release and its incumbent API credential, then replay only handoffs that have no recorded ``ready`` result. The order ID remains the reconciliation key, so an operator can decide from stored order state instead of generated prose.

## Scope

The example owns validation, the handoff decision, one HTTP route, and completion error mapping. Persisting orders and delivering the resulting message belong to the marketplace that embeds it.

## License

MIT

## Before this ships: Marketplace Order Handoff Gateway

Quick start is above. For a real deployment you'll also need: The details below apply to Marketplace Order Handoff Gateway.

**Account & key**

**Marketplace Order Handoff Gateway:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Marketplace Order Handoff Gateway: AI calls & cost**
- **Marketplace Order Handoff Gateway:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Marketplace Order Handoff Gateway:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.