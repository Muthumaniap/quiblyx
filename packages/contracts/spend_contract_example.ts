// Server-side only. Tokens grant scoped spend and must never enter a browser bundle.
const controlHeaders = {Authorization: `Bearer ${process.env.CONTROL_TOKEN}`, "Content-Type":"application/json"};
const base = process.env.CONTROL_URL ?? "http://127.0.0.1:8000";
const tenant = process.env.TENANT_ID!;
const created = await fetch(`${base}/api/v1/organisations/${tenant}/spend-contracts`, {method:"POST",
  headers:controlHeaders, body:JSON.stringify({name:"Resolve support ticket", purpose:"Approved answer",
  application_id:process.env.APPLICATION_ID, key_id:process.env.VIRTUAL_KEY_ID,
  max_cost_microusd:80000, max_tokens:4000, max_steps:4, allowed_models:["org-balanced"],
  allowed_tools:[], data_region:"local", duration_seconds:1800})});
if (!created.ok) throw new Error(`Contract creation failed: ${created.status}`);
const contract = await created.json();
const response = await fetch(`${process.env.GATEWAY_URL ?? "http://127.0.0.1:8001"}/v1/chat/completions`, {
  method:"POST", headers:{Authorization:`Bearer ${process.env.VIRTUAL_KEY}`, "Content-Type":"application/json",
  "Idempotency-Key":"support-ticket-42-answer", "X-Spend-Contract":contract.token,
  "X-Contract-Step":"answer"}, body:JSON.stringify({model:"org-balanced",
  messages:[{role:"user",content:"Draft the answer"}],max_tokens:500})});
if (!response.ok) throw new Error(`Contract step rejected: ${response.status}`);
export {};
