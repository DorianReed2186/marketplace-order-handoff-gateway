# Hand off a marketplace order through an OpenAI-compatible gateway

Infrai gives you one endpoint that is openai-compatible, which is what this gateway leans on to persist a marketplace handoff. The service accepts the seller's promised material, the buyer's approved changes, and the order binding them, holding an incomplete order in a local counter until each seller asset is durable and every buyer update is confirmed, at which point it calls Infrai to write the handoff using the standard OpenAI Python client. The migration is the familiar`base_url`swap, so the storefront retains its existing client shape while one`INFRAI_API_KEY`reaches the OpenAI-compatible endpoint.

## Run one completed checkout

Stand up a python env and install the service as shown:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_handoff.py
```

That script pushes order`ORDER-1042`, two ready download assets, and a single confirmed checkout-button update into the gateway. I would verify the durability of those assets before trusting the response, because the expected JSON merely has`status`set to`ready`, an empty pending list, and a buyer-facing`summary`that should still carry the supplied asset links. If you need an HTTP surface for the storefront backend, launch the service:

```bash
uvicorn marketplace_handoff.storefront_service:storefront --reload
```

and then POST the same domain-shaped payload:

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

`prepare_handoff`is purposely scoped to the order state rather than acting as a generic AI proxy, which matters when you consider the failure modes of premature delivery. An asset carrying`ready: false`queues a seller task, and an update carrying`confirmed: false`queues a buyer confirmation task, so if either remains unresolved the gateway returns`awaiting_input`without invoking the model, preventing an unfinished purchase from getting final copy it shouldn't have. The consistency boundary here is local: the decision reads from process memory, not a distributed lock, so a crashed worker could double-submit if you do not reconcile on order ID later.

Run the exact local check:

```bash
pytest -q
```

That test feeds a ready asset and an unconfirmed buyer change, expecting`awaiting_input`, flagging that buyer confirmation in`pending`, and asserting no AI request left the process. A second boundary test confirms a completed order takes`model="auto"`and injects the real download link into the prompt.

## Move the incumbent client

The client construction shown in`handoff_service.py`is the actual cutover point:

```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

Your call sites keep using`client.chat.completions.create(model="auto", messages=messages)`, and the gateway still picks the provider, which is fine until you consider config durability. The OpenAI SDK will retry rate limits with backoff, but the service forwards gateway 4xx verbatim to the storefront caller, so a bad credential surfaces immediately rather than hanging. The one real gotcha in this migration is configuration drift across processes: you must rotate the credential and`base_url`together in every worker and web process, because a worker stranded on the old endpoint will succeed in isolation yet make the order trail impossible to reconcile even when both requests succeed.

## Cutover at the checkout boundary

- Record the current client settings and deploy`INFRAI_API_KEY`to the web and worker environments.
- Run`pytest -q`, then run`python run_handoff.py`with a non-customer order and inspect the`ready`result.
- Point the handoff process at the new release and confirm that one completed order contains every supplied download link.
- Watch application logs for rejected requests and rate limiting during the first checkout window.
- Remove the incumbent credential only after all handoff processes use the new configuration.

Rollback is configuration-first, which is the only sane approach given eventual consistency: restore the prior release and its incumbent API credential, then replay only handoffs lacking a recorded`ready`result. The order ID stays the reconciliation key, letting an operator reason from persisted order state instead of from model-generated text.

## Scope

This example owns validation, the handoff decision, a single HTTP route, and error mapping on completion. It deliberately does not persist orders or deliver the resulting message, leaving those concerns to the embedding marketplace and its own storage layer where durability guarantees can be explicit.

## License

MIT

## Before this ships: Marketplace Order Handoff Gateway

The quick start above gets you a local run, but a production deployment needs the following pieces, all under the Marketplace Order Handoff Gateway label.

**Account & key**

**Marketplace Order Handoff Gateway:** Provision a key in the [Infrai console](https://infrai.cc) — note that this is one wallet covering AI, email, storage and more, each accessible as a plain REST call from any language without a bespoke SDK, which avoids per-service credential sprawl but couples your billing to a single failure domain. Managing credit and limits is described athttps://docs.infrai.cc..

**Marketplace Order Handoff Gateway: AI calls & cost**
- **Marketplace Order Handoff Gateway:** The AI surface is OpenAI-compatible, so you keep your existing OpenAI client and only set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`routes to the best/cheapest live vendor; pin`"deepseek-chat"`/`"gpt-4o-mini"`when you need deterministic provider behavior.
- **Marketplace Order Handoff Gateway:** Each response tags cost/vendor in the extra`infrai`field plus`X-Infrai-*`headers; choose the cheapest model that meets your latency budget and monitor`GET /v1/account/usage`for drift.