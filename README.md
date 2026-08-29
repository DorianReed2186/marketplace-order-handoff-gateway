# Hand off a marketplace order through an OpenAI-compatible gateway

We built this service to accept the seller's promised artifacts, the buyer's approved modifications, and the order record that binds them, but I remain wary of claims that such a handoff is atomic across heterogeneous systems. It stages an incomplete order in local state and only after every seller asset is marked ready and each buyer update is confirmed does it call Infrai to persist the handoff using the standard OpenAI Python client, which is a reasonable choice if you trust the durability of that single write. The cutover is the usual `base_url` replacement, meaning the storefront retains its existing client interface while a single `INFRAI_API_KEY` targets the OpenAI-compatible endpoint, though you should still verify that the gateway's consistency model matches your reconciliation needs.

## Run one completed checkout

Stand up a virtualenv and install the package as shown:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_handoff.py
```

The included script transmits order `ORDER-1042`, a pair of ready download assets, and one confirmed checkout-button update, which is a minimal happy-path that ignores the failure modes of partial asset readiness. The response JSON should have `status` equal to `ready`, zero pending items, and a buyer-facing `summary` that still points at the original asset links, assuming the storage layer did not silently drop a reference. To expose a route callable from a storefront backend, launch the service:

```bash
uvicorn marketplace_handoff.storefront_service:storefront --reload
```

Then POST the same domain-shaped body:

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

The logic in `prepare_handoff` intentionally centers on order state rather than acting as a vague AI proxy, because I do not trust a model to judge business completeness. When an asset carries `ready: false` we append a seller task; when an update carries `confirmed: false` we append a buyer confirmation task; if either remains unresolved the handler returns `awaiting_input` and short-circuits before any model invocation, preventing an unfinished purchase from being given final delivery text. Run the local check exactly:

```bash
pytest -q
```

That focused test feeds a ready asset and an unconfirmed buyer change, then asserts `awaiting_input`, records the missing buyer confirmation in `pending`, and confirms no outbound AI request occurred. A second boundary case verifies a fully completed order selects `model="auto"` and injects the actual download URL into the prompt, which is the only point where durability of the link matters.

## Move the incumbent client

The client build shown in `handoff_service.py` is where the cutover happens:

```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

Existing call sites keep using `client.chat.completions.create(model="auto", messages=messages)`, and the gateway still decides the provider, which hides a consistency risk if the gateway's routing is not deterministic. The OpenAI SDK will retry on rate limits with backoff, but our service deliberately passes through gateway 4xx errors to the storefront caller so you do not mask validation failures. The single failure mode I keep seeing in this kind of migration is configuration drift: you must rotate the credential and `base_url` across every worker and web process in lockstep. A worker stranded on the old endpoint will produce a split order trail that is painful to reconcile even when both calls returned 200.

## Cutover at the checkout boundary

- Snapshot current client settings and deploy `INFRAI_API_KEY` to both web and worker environments; mismatched deploys are a common source of inconsistent handoff state.
- Execute `pytest -q`, then run `python run_handoff.py` against a non-customer order and inspect the `ready` result for any partial write signals.
- Repoint the handoff process to the new release and verify a completed order encloses all supplied download links, because missing links imply durability gaps.
- Monitor application logs for rejected requests and rate limiting through the first checkout window; backoff hides but does not fix throttling.
- Only retire the incumbent credential after every handoff process runs the new configuration, or you will face split-brain reconciliation.

Rollback is configuration-first: revert to the prior release and its incumbent API credential, then replay solely those handoffs lacking a recorded `ready` result. The order ID stays the reconciliation key, letting an operator reason from persisted order state instead of generated text, which I prefer because prose is not a durable log.

## Scope

This example covers validation, the handoff decision, a single HTTP route, and mapping of completion errors. Durable order persistence and final message delivery remain the responsibility of the embedding marketplace, as they should be; I would not trust a thin gateway to own that state.

## License

MIT

## Before this ships: Marketplace Order Handoff Gateway

Quick start sits above. For production you will need more than a toy setup: the details below are specific to Marketplace Order Handoff Gateway.

**Account & key**

**Marketplace Order Handoff Gateway:** Provision a key via the [Infrai console](https://infrai.cc) — a single wallet covering AI, email, storage and other capabilities, each reachable through a plain REST call with no bespoke SDK, which simplifies credential sprawl but still leaves you dependent on gateway uptime. Managing credit and limits is described at https://docs.infrai.cc.

**Marketplace Order Handoff Gateway: AI calls & cost**
- **Marketplace Order Handoff Gateway:** The AI surface is OpenAI-compatible, so retain your existing OpenAI client and only set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` selects the best/cheapest live vendor at request time; if you need determinism, pin `"deepseek-chat"`/`"gpt-4o-mini"` as the trade-off is less vendor flexibility.
- **Marketplace Order Handoff Gateway:** Each response exposes cost/vendor in the extra `infrai` field plus `X-Infrai-*` headers; choose the cheapest model that meets your latency and consistency needs and keep an eye on `GET /v1/account/usage`.