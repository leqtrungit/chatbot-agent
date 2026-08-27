# Agent Harness Platform — Product Specification (v2)

| | |
|---|---|
| **Trạng thái** | 🔍 v0.1 DRAFT — đang review, chưa chốt |
| **Thay thế** | Định hướng lại toàn bộ sản phẩm; `PRODUCT_OVERVIEW.md` trở thành tài liệu tham chiếu v1 (legacy) |
| **Quy ước đọc** | Mục đánh dấu `[CẦN CHỐT]` là quyết định đang chờ owner duyệt. FR/NFR có ID để mọi task implementation trace ngược về đây. |

---

## 1. Tinh thần dự án (Project Spirit)

Xây dựng **nền tảng SaaS quản lý và vận hành AI Agent (Agent Harness) cho doanh nghiệp** — tự sở hữu harness từ gốc, không đứng trên framework agent của bên thứ ba.

Ba tinh thần cốt lõi, theo thứ tự ưu tiên khi phải đánh đổi:

1. **Agentic thật sự** — Agent là một *thực thể có vòng đời*, không phải một function call. Đơn vị trung tâm của toàn hệ thống là **Run**: một lần thực thi agent, durable, ghi lại từng bước (event-sourced). Mọi năng lực tương lai (asking, escalation, approval, trigger, multi-agent) đều là mở rộng tự nhiên của Run — không phải feature bolt-on.
2. **Manage** — Doanh nghiệp nhìn thấy và điều khiển được *mọi thứ* từ trang quản trị: agent làm gì, nghĩ gì, gọi tool nào, tốn bao nhiêu, lỗi ở đâu, dừng nó lại được không.
3. **Integrate** — Nhúng vào ứng dụng sẵn có của khách hàng phải *nhanh và liền mạch*, trước hết dưới dạng giao diện chat. Tích hợp là hai chiều: platform gọi ra ngoài (MCP, tools) và thế giới gọi vào platform (embed, API).

**Triết lý kỹ thuật bất biến** (mọi implementation agent phải tuân thủ, không có ngoại lệ):

- **Run-centric**: mọi lần agent chạy đều là một Run trong DB. Không có đường tắt "gọi LLM trực tiếp cho nhanh".
- **Agent core là pure library**: không import FastAPI/SQLAlchemy/framework. Hợp đồng của core là *"đưa state hiện tại → trả về quyết định tiếp theo"*; ai lưu state, ai schedule là việc của harness bên ngoài.
- **Postgres là source of truth duy nhất. Redis chỉ là transport** (queue, pub/sub, rate limit, cache). Redis chết → mất live-stream vài giây, không mất dữ liệu.
- **Multi-tenant từ dòng migration đầu tiên**: mọi bảng nghiệp vụ có `org_id`, mọi query scoped theo org. Không có "để sau".
- **TDD**: test viết trước, LLM/embedding luôn mock trong test, suite xanh ở mọi milestone.
- **Kỷ luật milestone chống second-system effect**: chỉ build đúng scope milestone hiện tại; ý tưởng hay ho khác ghi vào backlog (§10).

---

## 2. Bối cảnh & mục tiêu kinh doanh

### 2.1 Bài toán

Các harness/agent framework hiện có chủ yếu phục vụ cá nhân developer (CLI, desktop) hoặc là SDK phải tự vận hành. Doanh nghiệp muốn đưa AI agent vào ứng dụng của họ đang thiếu một nền tảng: (a) nhúng nhanh vào app sẵn có, (b) có trang quản trị để đội vận hành kiểm soát agent như kiểm soát một nhân viên — cấu hình, giám sát, can thiệp, (c) chịu tải production, không phải demo.

### 2.2 Khách hàng mục tiêu

Doanh nghiệp vừa và nhỏ đã có ứng dụng riêng (web/app), muốn thêm năng lực AI agent (trước hết: chat hỗ trợ khách hàng / trợ lý nghiệp vụ trên tri thức nội bộ) mà không xây đội AI riêng. `[CẦN CHỐT — segment cụ thể hơn: ngành nào trước? thị trường VN hay global?]`

### 2.3 Business targets theo giai đoạn `[CẦN CHỐT — toàn bộ mục này là đề xuất khung, owner điền/sửa]`

| Giai đoạn | Target | Tương ứng milestone |
|---|---|---|
| A — Foundation | Platform chạy end-to-end, demo được: tạo org → tạo agent → nhúng widget vào một app mẫu → chat có trace đầy đủ | M0–M2 |
| B — Design partner | 1–3 doanh nghiệp pilot dùng thật (miễn phí/giá tượng trưng), vòng lặp feedback hàng tuần | M3–M5 |
| C — Commercial | Định giá, self-serve onboarding, khách trả phí đầu tiên | sau v2 |

### 2.4 Thước đo thành công của v2 (product-level)

- Một developer của khách hàng nhúng được chat widget vào app của họ trong **< 30 phút** kể từ khi nhận API key (tính cả đọc docs).
- Tenant admin trả lời được câu hỏi *"agent vừa làm gì, vì sao trả lời như vậy, tốn bao nhiêu"* cho **bất kỳ** lượt chat nào, chỉ bằng trang quản trị.
- Hệ thống chịu được tải mục tiêu (§7 NFR-S) mà một tenant quá tải **không** làm nghẽn tenant khác.

---

## 3. Personas & Principals

Hệ thống phân biệt 4 loại chủ thể ngay từ tầng auth — đây là khác biệt nền tảng so với v1 (chỉ có admin + API key):

| # | Principal | Là ai | Xác thực bằng | Phạm vi quyền |
|---|---|---|---|---|
| P1 | **Platform Operator** | Chủ SaaS (ta) | tài khoản operator | Tạo/quản lý org, nhìn health toàn hệ thống. KHÔNG đọc nội dung hội thoại của tenant. |
| P2 | **Tenant Admin** | Nhân viên doanh nghiệp khách | email + password, thuộc 1 org | Toàn quyền trong org của mình: agents, knowledge, keys, xem trace/hội thoại, quota |
| P3 | **Integration** | Backend của khách (máy) | API key (server-side only) | Đổi token cho end-user, gọi API chat server-to-server. **API key không bao giờ xuất hiện trong browser** |
| P4 | **End-user** | Khách hàng của khách hàng | end-user token ngắn hạn (JWT, do P3 mint qua token exchange) | Chat với agent được phép; chỉ đọc hội thoại **của chính mình** |

---

## 4. Khái niệm cốt lõi (Domain Model)

```
Organization (tenant)
 ├── Users (P2, role: owner | admin)
 ├── ApiKeys (P3)
 ├── Agents ──── cấu hình: provider, model, credentials, system prompt,
 │               params, tools (knowledge_search, MCP), max_iterations
 ├── KnowledgeBases (v1 gọi là Domain) ── Documents ── Chunks (pgvector)
 ├── McpServers
 ├── EndUsers (P4, định danh do khách khai báo qua token exchange)
 ├── Conversations ── thuộc về (agent, end_user); lịch sử server-managed
 └── Runs ── ⭐ TRUNG TÂM ── một lần thực thi agent
      └── RunEvents (append-only): llm_call, llm_result, tool_call,
          tool_result, token_usage, error, state_change, ...
```

**Run state machine** (v2 chỉ implement các state không đánh dấu ⏳):

```
pending → running → succeeded | failed | cancelled
                  ↘ waiting_input ⏳ (reserved: asking/HITL — future)
                  ↘ waiting_approval ⏳ (reserved: escalation — future)
```

- Run được worker **claim theo lease + heartbeat**. Worker chết → lease hết hạn → worker khác claim lại, dựng lại state từ RunEvents (transcript chính là state) và chạy tiếp từ step cuối đã hoàn tất.
- **Conversation vs Run**: một Conversation gồm nhiều Run (mỗi message của end-user tạo một Run). Trace theo Run; lịch sử chat theo Conversation.

---

## 5. Phạm vi sản phẩm v2

### 5.1 v2 LÀ

- Nền tảng multi-tenant quản lý + vận hành agent, chat-first, nhúng được.
- Run engine durable với trace đầy đủ từng bước.
- Trang quản trị cho tenant: agents, knowledge, keys, quota, trace, hội thoại, usage.
- Embed surface: token exchange + chat API/SSE + widget.

### 5.2 v2 KHÔNG LÀ (non-goals — từ chối mọi scope-creep vào các mục này)

| Non-goal | Ghi chú |
|---|---|
| LLM hosting | Khách mang endpoint/key của họ (OpenAI-compat, Ollama self-host...) |
| Billing/subscription engine | Giai đoạn C |
| Asking / escalation / HITL | State đã reserve trong Run; KHÔNG implement ở v2 |
| Trigger ngoài chat (cron, webhook-event, agent gọi agent) | Kiến trúc Run đã sẵn chỗ; KHÔNG implement ở v2 |
| Agent memory ngoài lịch sử hội thoại | Future |
| Expose platform thành MCP server / OpenAI-compat API | Future |
| Channel adapters (Telegram/Slack/Zalo) | Sau khi embed surface ổn định |
| Self-serve signup, SSO/SAML, audit log chuẩn compliance | Giai đoạn C |
| Mobile SDK | Chỉ web widget ở v2 |

---

## 6. Functional Requirements

Ký hiệu độ ưu tiên: **[M]** must-have của v2 — thiếu là chưa xong v2; **[S]** should-have — làm nếu không lệch timeline; **[F]** future — chỉ ghi để giữ chỗ thiết kế.

### FR-T — Tenancy & Identity (Milestone M0)

- **FR-T1 [M]** Platform operator tạo/suspend organization. (Self-serve signup: [F])
- **FR-T2 [M]** Tenant user đăng nhập bằng email + password (JWT session). Org owner tạo được tài khoản cho thành viên khác (chưa cần email verification/reset — [S]).
- **FR-T3 [M]** Role tối thiểu: `owner` (quản lý user + mọi quyền admin), `admin` (mọi quyền trừ quản lý user).
- **FR-T4 [M]** API key: tạo/thu hồi theo org; hiển thị đúng một lần lúc tạo; lưu dạng hash.
- **FR-T5 [M]** Mọi resource thuộc đúng một org; mọi API đọc/ghi đều scoped theo org của principal; cross-org access bị chặn ở tầng query (không chỉ ở router).

### FR-A — Agent & Knowledge Management (M0 port + M3 UI)

- **FR-A1 [M]** CRUD Agent: provider (`ollama`/`openai`), model, base_url, api_key, system prompt (free text, dùng verbatim), sampling params, max_iterations, bật/tắt knowledge_search. *(Port từ v1, thêm org-scoping)*
- **FR-A2 [M]** CRUD KnowledgeBase + upload document (PDF/DOCX/TXT/MD) → ingest async → trạng thái pending/processing/completed/failed. *(Port từ v1)*
- **FR-A3 [M]** Gán agent ↔ knowledge base (n-n); agent nhiều KB dùng tool search có tham số chọn KB (hành vi v1 giữ nguyên). Gán agent ↔ MCP server. *(Port từ v1)*
- **FR-A4 [M]** Deactivate agent (soft): agent inactive từ chối mọi request chat mới.
- **FR-A5 [S]** Re-ingest / retry document lỗi từ UI.

### FR-R — Run Engine (M1) ⭐ trái tim của v2

- **FR-R1 [M]** Mỗi lần agent thực thi là một Run bền vững trong Postgres, với RunEvents append-only ghi: từng LLM call (request tóm tắt + response), từng tool call + kết quả, usage, lỗi, chuyển state.
- **FR-R2 [M]** Run state machine như §4; state `waiting_*` được định nghĩa trong enum/schema nhưng không có đường vào ở v2.
- **FR-R3 [M]** Worker claim Run bằng lease + heartbeat. Worker chết → Run được claim lại và **tiếp tục từ step cuối đã hoàn tất** (dựng lại transcript từ RunEvents), tối đa N lần retry (config), quá N → `failed` kèm trace nguyên vẹn.
- **FR-R4 [M]** Cancel Run: tenant admin (UI) hoặc integration (API) huỷ được Run đang `pending`/`running`; worker dừng ở checkpoint kế tiếp; Run → `cancelled`, trace giữ nguyên.
- **FR-R5 [M]** Mỗi Run có event stream realtime (Redis pub/sub → SSE): token deltas, tool activity, state change, done/error. Consumer: widget end-user (token) và trace viewer admin (live tail).
- **FR-R6 [M]** Run kết thúc ghi nhận: usage tổng (tokens), citations, stop reason, duration, số iteration.
- **FR-R7 [M]** Agent loop bên trong Run giữ các tính chất v1: tool errors không crash loop (thành tool_result lỗi), tool calls chạy concurrent, max_iterations guard.

### FR-C — Chat & Embed Surface (M2)

- **FR-C1 [M]** Token exchange: `POST /v2/token` — backend khách (API key) gửi `end_user_id` (+ display metadata tuỳ chọn) → nhận end-user JWT ngắn hạn. EndUser record được upsert theo (org, end_user_id).
- **FR-C2 [M]** Chat API (end-user token): gửi message vào một conversation → tạo Run → SSE stream (queued → tokens → done kèm citations). Conversation lịch sử server-managed theo (agent, end_user, conversation_id).
- **FR-C3 [M]** Conversation API (end-user token): list + đọc lịch sử **chỉ của chính end-user đó**. (So với v1: vá lỗ "mọi API key đọc được mọi session".)
- **FR-C4 [M]** Web widget nhúng bằng `<script>` tag: khung chat nổi (floating bubble) hoặc inline container; nhận end-user token từ host app; streaming; theme cơ bản (màu chủ đạo, logo, vị trí) config qua tham số. Không SDK framework-specific ở v2 ([F]: React SDK).
- **FR-C5 [M]** Chat server-to-server (API key, không cần end-user token) cho tích hợp backend thuần — giữ tương đương webhook v1 nhưng đi qua Run engine.
- **FR-C6 [S]** Client-managed history mode (caller tự gửi mảng history, không persist) — port hành vi v1 nếu còn phù hợp với mô hình Conversation mới; nếu xung đột thiết kế thì defer và ghi rõ lý do.

### FR-O — Control Plane / Observability (M3)

- **FR-O1 [M]** Run list theo org: filter theo agent, status, khoảng thời gian; realtime cho run đang chạy.
- **FR-O2 [M]** Trace viewer: mở một Run xem từng step (prompt/response LLM, tool call args/result, usage, timing, lỗi). Nội dung trace lưu có kiểm soát: bật/tắt lưu full content theo agent + retention theo org (mặc định 30 ngày `[CẦN CHỐT]`).
- **FR-O3 [M]** Conversation viewer: tenant admin xem hội thoại end-users của org mình (phục vụ vận hành/QA).
- **FR-O4 [M]** Usage dashboard theo org: requests, tokens, breakdown theo agent/key/model/status/time. *(Port analytics v1, thêm org-scoping)*
- **FR-O5 [M]** Quota config theo org: rate limit per key/per end-user, concurrency cap, queue-depth. Operator đặt trần theo org; tenant admin phân bổ trong trần đó.
- **FR-O6 [S]** Export trace/conversation (JSON) phục vụ audit nội bộ của tenant.

### FR-L — Load & Fairness (M5, thiết kế từ M1)

- **FR-L1 [M]** Queue-depth guard: vượt ngưỡng → từ chối sớm 429 + `Retry-After` ngay lúc nhận message, không nhận rồi để chờ vô định.
- **FR-L2 [M]** Fair scheduling per-tenant: worker phân phối công bằng giữa các org (không FIFO toàn cục); concurrency cap per-org. Một org bão hoà không làm chết org khác.
- **FR-L3 [M]** Load test script trong repo làm baseline, chạy được lặp lại; kết quả ghi vào docs.

---

## 7. Non-Functional Requirements

Các con số là **đề xuất ban đầu** `[CẦN CHỐT]` — quan trọng là có con số để test chống lại, số có thể chỉnh sau baseline đầu tiên.

### NFR-SEC — Bảo mật & cách ly

- **NFR-SEC1** Zero cross-tenant access: không tồn tại API nào trả dữ liệu khác org của principal. Enforced ở data-access layer + có test cách ly riêng (test cố tình truy cập chéo phải fail).
- **NFR-SEC2** API key: chỉ dùng server-side, lưu hash (không plaintext), thu hồi có hiệu lực ≤ 60s (cache TTL).
- **NFR-SEC3** End-user token: JWT ngắn hạn (TTL mặc định 1h), scope tối thiểu (org, agent(s), end_user), ký bằng secret per-deployment. Widget/browser không bao giờ thấy API key.
- **NFR-SEC4** Secrets của tenant (agent api_key, MCP headers) mã hoá at-rest (v1 để plaintext — v2 bắt buộc).
- **NFR-SEC5** Password hash chuẩn (argon2/bcrypt); session JWT có exp + revoke được (logout).

### NFR-S — Scale & Performance

- **NFR-S1** API layer stateless, scale ngang không sticky session (SSE relay qua Redis pub/sub — mọi replica subscribe được mọi run).
- **NFR-S2** Baseline v2 phải đạt: **500 SSE connections đồng thời / 1 API replica** và **200 Run đồng thời / deployment** (workers scale ngang) với error rate < 1%.
- **NFR-S3** Latency phần platform (loại trừ độ trễ LLM provider): nhận message → SSE event `queued` **p95 < 300ms**; worker phát token → client nhận **p95 < 150ms**.
- **NFR-S4** Noisy neighbor: khi một org bão hoà quota, p95 time-to-first-token của org khác tăng **< 20%** so với baseline.

### NFR-R — Reliability & Durability

- **NFR-R1** Postgres = source of truth. Redis mất → không mất Run/RunEvent nào; live-stream gián đoạn rồi tự nối lại.
- **NFR-R2** Worker crash → Run được re-claim trong ≤ 60s (lease timeout); không có zombie run (chạy mãi không ai biết) và không có orphan run (pending mãi không ai nhận).
- **NFR-R3** Graceful shutdown: worker nhận SIGTERM chạy nốt step hiện tại, release lease sạch.
- **NFR-R4** Availability target giai đoạn design-partner: 99.5%/tháng, single region.

### NFR-O — Observability (của chính platform)

- **NFR-O1** Structured logging (JSON) toàn backend, có `org_id`/`run_id` correlation.
- **NFR-O2** Health endpoints (API, worker heartbeat) + metrics cơ bản (queue depth, run throughput, error rate) đủ để gắn Prometheus sau này.

### NFR-D — Data

- **NFR-D1** Retention nội dung trace/conversation config theo org; job xoá định kỳ. Mặc định: trace content 30 ngày, conversation không giới hạn `[CẦN CHỐT]`.
- **NFR-D2** Xoá org = xoá được toàn bộ dữ liệu org (cascade có chủ đích) — điều kiện tối thiểu cho cam kết dữ liệu với doanh nghiệp.

### NFR-T — Testability & Engineering

- **NFR-T1** TDD; LLM/embedding mock 100% trong test; suite xanh ở mọi milestone; CI (GitHub Actions) chạy pytest + FE build từ M0.
- **NFR-T2** Mọi task implementation phải reference FR/NFR ID trong PR/commit message.
- **NFR-T3** Agent core (pure library) không import framework — enforce bằng test kiến trúc (import-linter hoặc test tự viết).

---

## 8. Milestones & tiêu chí hoàn thành

| MS | Tên | Nội dung chính | Definition of Done |
|---|---|---|---|
| **M0** | Tenancy & Identity | orgs, users, login, roles, API keys, org-scoping toàn schema; CI; port Agent/KB CRUD (org-scoped) | Tạo org qua operator → login tenant admin → CRUD agent/KB trong org; test cách ly cross-tenant xanh; CI chạy trên PR |
| **M1** | Run Engine ⭐ | runs + run_events, state machine, claim/lease/heartbeat/resume, cancel, pub/sub stream; agent loop chạy trên engine (1 tool mock) | Kill worker giữa run → run resume và hoàn thành; cancel hoạt động; trace đọc được từ DB; stream SSE live |
| **M2** | Embed Surface | token exchange, EndUser, Conversation, chat API/SSE trên Run engine, widget nhúng, knowledge_search + MCP tools nối vào engine | App mẫu (host giả lập) nhúng widget, end-user chat có streaming + citations; end-user không đọc được hội thoại người khác |
| **M3** | Control Plane | run list, trace viewer, conversation viewer, usage dashboard, quota config (FE admin port + mở rộng) | Tenant admin trả lời được "agent vừa làm gì/vì sao/tốn bao nhiêu" hoàn toàn qua UI |
| **M4** | Hardening tools & ingestion | port đầy đủ ingestion niceties, MCP quản trị UI, secrets encryption, retention jobs | FR-A/S còn lại + NFR-SEC4 + NFR-D1 đạt |
| **M5** | Load & Fairness | fair scheduler per-org, queue-depth guard, load test, tuning | NFR-S2/S3/S4 đo được và đạt bằng load test lặp lại được |

Sau mỗi milestone: cập nhật `progress.md`, demo chạy được end-to-end trong phạm vi milestone.

**Chiến lược code**: greenfield-lõi trong cùng repo (nhánh `refactor/build-harness`). Xây mới `app` theo cấu trúc v2; **port** (copy-adapt) các module ngoại vi từ v1: provider adapters, MCP client, ingestion pipeline, rate limiter, SSE relay pattern, FE shell/components. Code v1 giữ nguyên trên `develop` làm tham chiếu; phần v1 trong nhánh v2 bị xoá dần khi module tương ứng đạt parity — **không nuôi hai đường chạy song song quá một milestone**.

---

## 9. Rủi ro chính & đối sách

| Rủi ro | Đối sách |
|---|---|
| Second-system effect (over-design vì tờ giấy trắng) | Kỷ luật §1; mọi đề xuất ngoài scope milestone → backlog §10; reviewer (owner) chặn ở PR |
| Run engine tự viết có bug concurrency khó lường (lease, resume, race) | M1 dành riêng; test mô phỏng crash/race là DoD bắt buộc; giữ semantics đơn giản (single-claimer lease, transcript-as-state) |
| Retrofit tenancy sót chỗ → lộ dữ liệu chéo tenant | Org-scoping nằm ở data-access layer dùng chung, không rải rác từng router; test cách ly chuyên biệt (NFR-SEC1) |
| Port module v1 kéo theo giả định single-tenant ngầm | Mỗi module port phải qua review + bổ sung test org-scoping trước khi merge |
| Widget chạy trên trang của khách (CSP, CORS, xung đột CSS) | Web component + shadow DOM; CORS config per-org; test trên app mẫu độc lập |
| Số NFR đặt sai (quá cao/thấp) | Baseline load test sớm (kéo một phần M5 lên chạy thô ngay sau M2), chỉnh số có căn cứ |

---

## 10. Backlog sau v2 (giữ chỗ, không làm)

Asking/HITL (`waiting_input`) · Escalation/approval (`waiting_approval`) · Triggers (cron/webhook/agent-to-agent) · Agent memory · Multi-agent orchestration · Expose MCP server + OpenAI-compat API · Channel adapters (Telegram/Zalo/Slack) · React SDK · Billing · Self-serve signup · SSO/SAML · Audit log compliance · Cost ($) analytics · Mobile SDK

---

## 11. Glossary

| Thuật ngữ | Nghĩa trong tài liệu này |
|---|---|
| **Harness** | Toàn bộ hạ tầng vận hành agent: run engine, scheduler, trace, quota, guardrails |
| **Run** | Một lần thực thi agent, durable, event-sourced — đơn vị trung tâm |
| **RunEvent** | Một bước trong Run (append-only) |
| **Tenant / Organization** | Một doanh nghiệp khách hàng |
| **End-user** | Người dùng cuối của tenant, chat qua widget/app của tenant |
| **Integration** | Backend của tenant, cầm API key |
| **Token exchange** | API key (server) đổi ra end-user JWT ngắn hạn (browser) |
| **KnowledgeBase** | Kho tri thức RAG (v1 gọi là Domain) |
| **Transcript-as-state** | Nguyên tắc: state của Run = chuỗi messages dựng lại từ RunEvents, nên resume = đọc lại event log |
