// Server-side only. Do not import this into a browser bundle.
const response = await fetch(`${process.env.GATEWAY_URL ?? "http://127.0.0.1:8001"}/v1/chat/completions`, {
  method: "POST",
  headers: {Authorization: `Bearer ${process.env.VIRTUAL_KEY}`, "Content-Type": "application/json", "Idempotency-Key": "example-1"},
  body: JSON.stringify({model:"org-balanced", messages:[{role:"user", content:"Hello"}], max_tokens:64})
});
if (!response.ok) throw new Error(`Gateway rejected request: ${response.status}`);
console.log(await response.json());
export {};
