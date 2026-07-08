---
name: add-channel-adapter
description: Add a new platform integration (Telegram, Slack, Zalo, Messenger, ...) to the webhook layer via a ChannelAdapter. Use whenever connecting the chatbot to a new external platform.
---

# Add a channel adapter

One platform = one `ChannelAdapter` subclass + registry entry. The webhook router, queue, worker, and agent need NO changes.

## TDD order

1. **Tests first** in `tests/channels/test_<platform>_adapter.py` (copy the style of `test_generic_adapter.py`):
   - happy path: platform's real payload shape → correct `IncomingMessage` (domain_id, session_id, text, metadata)
   - invalid payload → `ChannelParseError`
   - platform-specific quirks (signature headers, session/user id mapping into `session_id`, extra fields into `metadata`)
2. **Implement** `app/channels/<platform>.py`:
   - subclass `ChannelAdapter` (`app/channels/base.py`), set `platform = "<slug>"`
   - `parse_incoming(payload, headers)` → `IncomingMessage`; raise `ChannelParseError` on anything malformed. The domain is addressed by uuid **or slug** — decide how the platform conveys it (path? payload field? per-bot config) and document it in the class docstring.
   - `send_response(message)` — implement real push (platform API call via httpx) if the platform supports it; otherwise leave the inherited no-op and clients use job polling. Push calls must be mocked in tests (httpx MockTransport), never hit the network.
3. **Register** it in `app/channels/registry.py`'s default registry (next to `GenericAdapter`).
4. Add a webhook API test in `tests/modules/test_webhook_api.py` covering `POST /api/webhooks/<slug>` happy path (monkeypatch the enqueue helper, same pattern as existing tests).

## Constraints

- Adapters are stateless; secrets/tokens go through `Settings` (`app/core/config.py`) + `.env.example`, never hard-coded.
- Signature verification failures should raise `ChannelParseError` (surfaces as 422) or a dedicated 401 if you add one — but keep the router generic; platform specifics stay inside the adapter.
- Webhook routes have NO basic auth — external platforms call them.

## Done when

`cd backend && uv run pytest -q` fully green; run the /verify skill's smoke test with the new slug if the platform payload can be simulated with curl.
