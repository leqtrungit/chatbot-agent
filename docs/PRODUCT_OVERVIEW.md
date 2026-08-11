# PRD — Chatbot Agent Platform

| | |
|---|---|
| **Trạng thái tài liệu** | Draft, phản ánh trạng thái code tại 2026-08-11 |
| **Nguồn** | `CLAUDE.md`, `progress.md`, `git log`, mã nguồn `backend/app/` |
| **Phạm vi** | Toàn bộ nền tảng (backend FastAPI + admin frontend Next.js) |

---

## 1. Tóm tắt (TL;DR)

Nền tảng chatbot agent tri thức tổng quát, cấu hình hoàn toàn qua UI/API, không hardcode gì lúc deploy.

- Admin tạo **domain** (kho tri thức từ tài liệu upload) và **agent** (LLM provider/model/system prompt/tools tự chọn).
- Admin gán agent vào domain (nhiều-nhiều) và vào MCP server nếu cần tool ngoài.
- Nền tảng bên ngoài (Telegram, Zalo, Slack, web widget, hệ thống nội bộ...) gọi một webhook chung kèm `agent_id` để chat với agent đó; agent tự tra cứu domain được gán.

## 2. Bài toán & mục tiêu

**Bài toán**: mỗi lần cần một chatbot tri thức mới (domain khác, LLM khác, kênh khác) thường phải sửa code/redeploy. Muốn tách hoàn toàn phần *cấu hình* (domain nào, agent nào, provider nào, prompt gì) khỏi phần *runtime* (agent loop, webhook, job queue) để thêm agent/domain/kênh mới là thao tác cấu hình, không phải thay đổi mã nguồn.

**Mục tiêu**:
1. Admin tự phục vụ (self-service) toàn bộ vòng đời domain/agent qua UI — không cần đội kỹ thuật can thiệp code.
2. Một agent framework provider-agnostic — đổi/thêm LLM provider là thêm 1 adapter, không đụng agent loop.
3. Một hợp đồng tích hợp (integration contract) chung cho mọi nền tảng bên ngoài, qua `ChannelAdapter`.
4. Toàn bộ hành vi có thể kiểm chứng bằng test tự động (không phụ thuộc "chạy thử bằng tay mới biết đúng").

**Ngoài phạm vi (non-goals)** ở giai đoạn hiện tại:
- Không tự xây UI chat cho end-user (nền tảng bên ngoài tự làm UI, chỉ gọi API).
- Không làm multi-tenant SaaS (chưa có khái niệm tổ chức/khách hàng tách biệt — một deployment phục vụ một tổ chức).
- Không tính chi phí ($) hay billing.

## 3. Người dùng / Persona

| Persona | Vai trò | Truy cập | Nhu cầu chính |
|---|---|---|---|
| **Admin nội bộ** | Cấu hình domain, agent, MCP server, theo dõi dashboard | Admin UI (Next.js), HTTP Basic Auth | Tạo/sửa agent nhanh, không cần biết code |
| **Đối tác tích hợp** | Đội kỹ thuật của nền tảng bên ngoài (Telegram bot, Zalo OA, hệ thống nội bộ...) | REST API, `X-API-Key` | Hợp đồng API ổn định, dễ tích hợp, tự quản lý session/history |
| **End-user cuối** | Người chat trên nền tảng bên ngoài | Gián tiếp qua đối tác tích hợp | Không tương tác trực tiếp với hệ thống này |

## 4. Yêu cầu chức năng (Functional Requirements)

| ID | Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|---|
| FR-1 | Admin tạo/sửa/xoá domain | ✅ Done | CRUD chuẩn, `app/modules/domain/` |
| FR-2 | Upload tài liệu (PDF/DOCX/TXT/MD) vào domain, pipeline ingest bất đồng bộ | ✅ Done | extract → chunk (overlap) → embed → lưu `document_chunks` (pgvector, HNSW, cosine); trạng thái `pending→processing→completed/failed` hiển thị trên UI |
| FR-3 | Admin tạo/sửa agent: provider, model, base_url/api_key, system_prompt tự do, sampling params, bật/tắt knowledge search | ✅ Done | `app/modules/agent/`; system prompt dùng verbatim, không tự chèn tên/mô tả domain |
| FR-4 | Gán agent ↔ domain (nhiều-nhiều), chỉnh từ cả hai phía | ✅ Done | `PUT /api/agents/{id}/domains` và `PUT /api/domains/{id}/agents` |
| FR-5 | Gán agent ↔ MCP server, tool từ MCP server tự khả dụng cho agent | ✅ Done | `app/modules/mcp/` |
| FR-6 | Agent có ≥2 domain: LLM tự chọn domain cần tra cứu theo từng câu hỏi (tham số enum động) | ✅ Done | Không có `domain_id` trong request từ bên ngoài — agent tự quyết định phạm vi |
| FR-7 | Webhook chung nhận tin nhắn, trả job bất đồng bộ | ✅ Done | `POST /api/webhooks/{platform}` → `202 {job_id}`, xem `docs/API_INTEGRATION.md` |
| FR-8 | Polling trạng thái job | ✅ Done | `GET /api/jobs/{job_id}` |
| FR-9 | Streaming phản hồi theo token (SSE) | ✅ Done | `POST /api/chat/stream` |
| FR-10 | Xác thực đối tác bằng API key, rate-limit theo key | ✅ Done | `X-API-Key`, `app/modules/apikey/` |
| FR-11 | Lịch sử hội thoại server-managed theo `(agent_id, session_id)` | ✅ Done | `app/modules/conversation/`, load trước khi chạy agent, append sau |
| FR-12 | Lịch sử hội thoại client-managed (đối tác tự gửi `history`, không persist) | ✅ Done | Field `history` vắng mặt = server-managed; có mặt (kể cả rỗng) = client-managed |
| FR-13 | API đọc lịch sử hội thoại cho bên thứ ba tự dựng UI | ✅ Done | `GET /api/conversations/{agent_id}/{session_id}/messages` |
| FR-14 | Cơ chế mở rộng nền tảng chat mới qua `ChannelAdapter` | ✅ Kiến trúc xong / ⚠️ Chỉ có 1 adapter thật | Hiện chỉ có `GenericAdapter`; thêm Telegram/Slack/Zalo cần code + đăng ký `ChannelRegistry` (`/add-channel-adapter`) |
| FR-15 | Request logging + dashboard usage analytics | ✅ Done | Bảng `request_logs` (token, model, provider, latency, thành công/lỗi — không lưu nội dung tin nhắn); trang `/dashboard` |
| FR-16 | Tính chi phí ($) trong dashboard | ❌ Chưa làm | Backlog |

## 5. Nguyên tắc kiến trúc (Design Tenets)

Áp dụng bắt buộc cho mọi thay đổi, không thương lượng:

1. **`app/agent/` là thư viện thuần** — không import FastAPI/SQLAlchemy/`app.core`/`app.modules`. Năng lực ngoài (LLM, vector search) vào qua protocol trừu tượng, implementation tiêm từ bên ngoài.
2. **Không hardcode gì cấu hình được** — đổi provider = thêm 1 adapter, không đụng agent loop/builder; system prompt luôn free-text per-agent.
3. **TDD bắt buộc** — test fail trước, code sau; LLM/embedding luôn mock trong test, không gọi service thật.
4. **Thay đổi cộng thêm (additive), không phá vỡ đường cũ** khi có thể — ví dụ client-managed history dùng "có/không có field `history`" làm tín hiệu, caller cũ không bị ảnh hưởng. Breaking change (như bỏ `domain_id` khỏi webhook) chỉ làm khi thực sự cần và công bố rõ.
5. **Ba luồng auth tách bạch** — ingestion (admin, basic auth), quản lý agent (admin, basic auth), chat (đối tác, `X-API-Key`) — chia sẻ DB, không rò rỉ logic.
6. **Xác nhận bằng chạy thật, không chỉ unit test** — thay đổi lớn kèm smoke test trên Postgres/worker container thật trước khi coi là xong.

## 6. Luồng sử dụng chính (User Flow)

1. Admin tạo domain (vd: "Chính sách nhân sự").
2. Admin upload tài liệu vào domain, theo dõi trạng thái ingest trên UI.
3. Admin tạo agent: chọn provider/model, viết system prompt, cấu hình sampling params.
4. Admin gán agent vào domain (một hoặc nhiều).
5. (Tuỳ chọn) Admin gán MCP server cho agent.
6. Admin cấp API key + `agent_id` cho đối tác tích hợp.
7. Đối tác gọi webhook hoặc `/api/chat/stream` — đi live.

## 7. Use case mục tiêu

- Chatbot hỗ trợ khách hàng dựa trên tài liệu nội bộ (FAQ, bảo hành, hướng dẫn sản phẩm).
- Trợ lý nội bộ tra cứu tài liệu công ty (chính sách nhân sự, quy trình, tài liệu kỹ thuật) qua Slack/Teams.
- Một agent phục vụ nhiều mảng tri thức cùng lúc (multi-domain), không cần dựng nhiều bot riêng.
- Tích hợp nhanh nhiều kênh chat (Telegram, Zalo, web) dùng chung một backend, một bộ agent.

## 8. Trạng thái hiện tại (tính đến 2026-08-11)

- 271 test backend pass, frontend build sạch.
- Core đã ổn định: ingestion, domain/agent/MCP CRUD, webhook + job queue, SSE streaming, auth + rate-limit, lịch sử hội thoại (2 chế độ), request logging + dashboard.

## 9. Gap & rủi ro đã biết

| Gap | Ảnh hưởng | Ưu tiên gợi ý |
|---|---|---|
| Chỉ có `GenericAdapter`, chưa có Telegram/Slack/Zalo adapter thật | Không tích hợp được kênh thật ngay | Cao — backlog kế tiếp |
| Chưa có CI tự động (branch protection `main` chỉ bắt buộc PR, không gate test) | Rủi ro merge code fail test | Cao |
| `api_key`/`headers` của agent và MCP server lưu plaintext, chưa mã hoá at-rest | Rủi ro bảo mật nếu DB bị lộ | Cao |
| API key chưa scope theo agent/domain cụ thể — 1 key hợp lệ gọi được mọi agent | Rủi ro nếu key của một đối tác bị lộ | Trung bình |
| Admin auth vẫn basic auth đơn giản (`admin/admin` mặc định), chưa có multi-admin/user account | Không phù hợp nhiều người quản trị | Trung bình |
| Chưa có deployment thật ngoài docker compose local | Chưa sẵn sàng production | Trung bình |
| Chưa tính chi phí ($) trong dashboard | Thiếu visibility chi phí vận hành | Thấp |

## 10. Câu hỏi mở

- Kênh nào (Telegram/Zalo/Slack) ưu tiên làm adapter thật trước?
- Có cần multi-tenant (nhiều tổ chức trên cùng deployment) trong roadmap gần không?
- Chiến lược mã hoá secret at-rest: dùng KMS ngoài hay mã hoá app-level?
