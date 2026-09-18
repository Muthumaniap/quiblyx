# Provider support matrix

Status 2026-09-17. "Implemented" does not imply live-provider qualification.

| Provider | Text | SSE | Tools / structured output | Embeddings / media | Usage / reconciliation |
|---|---|---|---|---|---|
| Deterministic mock | Implemented | Implemented | Rejected | Rejected | Synthetic bounded units; uncertain costs retained |
| OpenAI | Not implemented | Not implemented | Not implemented | Not implemented | No price assumptions |
| Azure OpenAI | Not implemented | Not implemented | Not implemented | Not implemented | Not qualified |
| Anthropic | Not implemented | Not implemented | Not implemented | Not implemented | Not qualified |
| Gemini | Not implemented | Not implemented | Not implemented | Not implemented | Not qualified |
| Bedrock | Not implemented | Not implemented | Not implemented | Not implemented | Not qualified |
| Self-hosted | Not implemented | Not implemented | Not implemented | Not implemented | Requires controlled egress design |

Mock is entirely in-process and cannot incur paid provider charges. Fault selection is a mock-only field. No automatic retry or fallback is implemented. A failed stream remains uncertain and has no completion sentinel. Repeating its idempotency key returns 409 rather than dispatching again.

Gateway compatibility: only system/user/assistant text messages, model alias, max_tokens and stream. Unknown parameters including tools and response_format return schema errors before admission. Caller-supplied user identity is rejected. Response metadata identifies mock-text-v1 and synthetic mock-v1 prices. Broader OpenAI compatibility is not claimed.
