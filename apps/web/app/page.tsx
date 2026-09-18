"use client";
import { useState } from "react";
import { brand } from "./brand";

type Row = Record<string, string | number | boolean | null>;
const api = process.env.NEXT_PUBLIC_CONTROL_URL || "http://localhost:8000";

export default function Console() {
  const [token, setToken] = useState("");
  const [tenant, setTenant] = useState("");
  const [name, setName] = useState("");
  const [retention, setRetention] = useState("0");
  const [budget, setBudget] = useState("1000000");
  const [tab, setTab] = useState("Overview");
  const [summary, setSummary] = useState<Row | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [secret, setSecret] = useState("");
  const [connection, setConnection] = useState("");
  const [application, setApplication] = useState("");
  const [parent, setParent] = useState("");
  const [unit, setUnit] = useState("money");
  const [cadence, setCadence] = useState("month");
  const [version, setVersion] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [requestId, setRequestId] = useState("");
  const [detail, setDetail] = useState<object | null>(null);

  async function call(path: string, method = "GET", body?: object) {
    const response = await fetch(api + path, {method, headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`}, body: body ? JSON.stringify(body) : undefined, cache: "no-store"});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : JSON.stringify(value.detail));
    return value;
  }
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  const base = `/api/v1/organisations/${tenant}`;
  async function refresh(next = tab) {
    setTab(next);
    if (next === "Overview") setSummary(await call(base + "/usage"));
    else {
      const map: Record<string, string> = {Requests:"requests", Groups:"groups", Providers:"provider-connections", Applications:"applications", Keys:"virtual-keys", Budgets:"budgets", Audit:"audit-events", Notifications:"notifications"};
      setRows((await call(base + "/" + map[next])).items);
    }
  }
  return <div className="shell">
    <aside><a className="brand" href="/" aria-label={`${brand.name} home`}><img src={brand.mark} alt="" width={42} height={42}/><span>{brand.name.toLowerCase()}</span></a><p className="eyebrow">WORKSPACE CONTROL</p>
      {["Overview","Requests","Groups","Providers","Applications","Keys","Budgets","Notifications","Audit"].map(item => <button className={tab === item ? "nav active" : "nav"} key={item} disabled={!tenant || busy} onClick={() => act(() => refresh(item))}>{item}</button>)}
      <div className="aside-foot"><span className="dot"/> Local development<br/><small>Deterministic mock providers</small></div>
    </aside>
    <main><header><div><p className="eyebrow">ORGANISATION / {tenant ? tenant.slice(0,8) : "GET STARTED"}</p><h1>{tenant ? tab : "Your AI, under control."}</h1></div><span className="badge">MOCK MODE · NO PAID CALLS</span></header>
      <section className="panel credentials"><label>Development access token<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} placeholder="DEV_LOGIN_TOKEN from your local .env"/></label><label>Existing organisation ID<input value={tenant} onChange={e => setTenant(e.target.value)} placeholder="Create below or enter an ID"/></label><button disabled={busy || !tenant || !token} onClick={() => act(() => refresh())}>Connect</button></section>
      <p className="muted">Local identity adapter. Token stays in memory. OIDC browser sign-in is not yet available.</p>
      {error && <div role="alert" className="error">{error}</div>}{notice && <div role="status" className="notice">{notice}</div>}{busy && <p role="status">Working…</p>}
      {!tenant && <section className="panel onboarding"><p className="eyebrow">01 / CREATE YOUR WORKSPACE</p><h2>Start with a safe spending limit.</h2><p>Provider costs below are simulated. Every request reserves funds before it runs.</p><label>Organisation name<input value={name} onChange={e => setName(e.target.value)} placeholder="Acme Research"/></label><label>Monthly budget (USD micro-units)<input type="number" min="0" value={budget} onChange={e => setBudget(e.target.value)}/></label><label>Content retention choice<select value={retention} onChange={e => setRetention(e.target.value)}><option value="0">Do not retain content</option><option value="30">30 days (storage not yet enabled)</option></select></label><button disabled={busy || !token || !name} onClick={() => act(async () => {const org = await call("/api/v1/organisations", "POST", {name, content_days:Number(retention), budget_microusd:Number(budget)}); setTenant(org.id); setNotice("Organisation created. Connect a mock provider next.");})}>Create organisation →</button></section>}
      {tenant && tab === "Overview" && <><div className="metrics">{[["Settled spend",summary?.spent_microusd],["Reserved spend",summary?.reserved_microusd],["Monthly limit",summary?.hard_limit_microusd]].map(([label,value]) => <section className="panel metric" key={String(label)}><p>{label}</p><strong>{value === undefined ? "—" : `$${(Number(value)/1e6).toFixed(6)}`}</strong><small>USD · {summary?.period || "Refresh to load"}</small></section>)}</div><section className="panel"><p className="eyebrow">NEXT STEPS</p><h2>Connect your first application</h2><p>Create a mock provider, create an application, then issue its server key. Use the gateway example below and refresh usage to see settled costs.</p><div className="actions"><button onClick={() => act(() => refresh("Providers"))}>1. Provider</button><button onClick={() => act(() => refresh("Applications"))}>2. Application</button><button onClick={() => act(() => refresh("Keys"))}>3. Virtual key</button><button onClick={() => act(() => refresh())}>Refresh usage</button></div></section></>}
      {tenant && ["Providers","Applications","Groups","Keys"].includes(tab) && <section className="panel"><h2>Create {tab === "Keys" ? "virtual key" : tab.toLowerCase().replace(/s$/,"")}</h2>
        {tab !== "Keys" && <label>Name<input value={name} onChange={e => setName(e.target.value)}/></label>}
        {tab === "Applications" && <label>Provider connection ID<input value={connection} onChange={e => setConnection(e.target.value)}/></label>}
        {["Applications","Groups"].includes(tab) && <label>{tab === "Groups" ? "Parent group" : "Billing group"} ID (optional)<input value={parent} onChange={e => setParent(e.target.value)}/></label>}
        {tab === "Keys" && <label>Application ID<input value={application} onChange={e => setApplication(e.target.value)}/></label>}
        <button disabled={busy} onClick={() => act(async () => {
          const resource = {Providers:"provider-connections",Applications:"applications",Groups:"groups",Keys:"virtual-keys"}[tab as "Providers"];
          const body = tab === "Providers" ? {name,provider:"mock"} : tab === "Applications" ? {name,connection_id:connection,group_id:parent || null} : tab === "Groups" ? {name,parent_id:parent || null} : {application_id:application};
          const row = await call(base+"/"+resource,"POST",body);
          if (tab === "Providers") setConnection(row.id);
          if (tab === "Applications") setApplication(row.id);
          if (row.secret) setSecret(row.secret);
          await refresh();
        })}>Create {tab === "Providers" ? "mock connection" : "record"}</button></section>}
      {secret && <section className="panel secret"><h2>Copy your virtual key now</h2><p>This secret is displayed once. Store it in your server environment.</p><code>{secret}</code><button onClick={() => setSecret("")}>I have saved it — dismiss</button></section>}
      {tenant && tab === "Budgets" && <section className="panel"><h2>Set an inherited hard limit</h2><p>Requests must fit every applicable organisation, group and application cap. A reduction below committed usage blocks new requests. Existing reservations remain accounted for.</p><label>Scope ID (blank = organisation)<input value={parent} onChange={e => setParent(e.target.value)}/></label><label>Unit<select value={unit} onChange={e => setUnit(e.target.value)}><option value="money">USD micro-units</option><option value="tokens">Tokens (synthetic in mock mode)</option><option value="requests">Requests</option></select></label><label>UTC period<select value={cadence} onChange={e => setCadence(e.target.value)}><option value="month">Current calendar month</option><option value="day">Current calendar day</option></select></label><label>Hard limit<input type="number" min="0" value={budget} onChange={e => setBudget(e.target.value)}/></label><label>Current version (0 to create; see table to update)<input type="number" min="0" value={version} onChange={e => setVersion(e.target.value)}/></label><button disabled={busy} onClick={() => {if (confirm(`Apply ${budget} ${unit} per ${cadence} to scope ${parent || tenant}? New requests may be blocked; in-flight reservations remain.`)) act(async () => {await call(base+"/budgets","POST",{scope_id:parent || tenant,hard_limit:Number(budget),version:Number(version),unit,cadence}); await refresh(); setNotice("Budget saved. Ancestor limits continue to apply.");});}}>Review and apply limit</button></section>}
      {tenant && tab === "Requests" && <section className="panel"><h2>Inspect request accounting</h2><label>Request ID<input value={requestId} onChange={e => setRequestId(e.target.value)}/></label><div className="actions"><button disabled={busy || !requestId} onClick={() => act(async () => setDetail(await call(base+`/requests/${requestId}`)))}>Inspect reservations and ledger</button><button disabled={busy || !requestId} onClick={() => {if (confirm(`Charge the entire reserved maximum for uncertain request ${requestId}? This conservative adjustment consumes the full bound and cannot be undone through this action.`)) act(async () => {await call(base+`/requests/${requestId}/reconcile-conservative`,"POST"); setDetail(await call(base+`/requests/${requestId}`)); await refresh();});}}>Reconcile uncertain request at full bound</button></div>{detail && <pre>{JSON.stringify(detail,null,2)}</pre>}</section>}
      {tenant && tab !== "Overview" && <section className="panel"><div className="table-head"><h2>{tab}</h2><button onClick={() => act(() => refresh())} disabled={busy}>Refresh</button></div>{rows.length === 0 ? <p className="empty">No records yet.</p> : <div className="table-wrap"><table><thead><tr>{Object.keys(rows[0]).map(key => <th key={key}>{key.replaceAll("_"," ")}</th>)}{["Keys","Applications"].includes(tab) && <th>Actions</th>}</tr></thead><tbody>{rows.map(row => <tr key={String(row.id)}>{Object.entries(row).map(([key,value]) => <td key={key}>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</td>)}{tab === "Keys" && <td><button disabled={Boolean(row.revoked)} onClick={() => {if (confirm(`Revoke key ${row.prefix}? New requests will fail; in-flight requests may finish.`)) act(async () => {await call(base+`/virtual-keys/${row.id}/revoke`,"POST"); await refresh();});}}>Revoke</button></td>}{tab === "Applications" && <td><button onClick={() => act(async () => {await call(base+`/applications/${row.id}`,"PATCH",{paused:!row.paused}); await refresh();})}>{row.paused ? "Resume" : "Pause"}</button></td>}</tr>)}</tbody></table></div>}</section>}
      {tenant && <section className="panel"><h2>Make a gateway request</h2><p>Run from your application server. The console never sends virtual keys to the gateway.</p><pre>{`curl http://localhost:8001/v1/chat/completions \\\n  -H "Authorization: Bearer $VIRTUAL_KEY" \\\n  -H "Content-Type: application/json" \\\n  -H "Idempotency-Key: first-request" \\\n  -d '{"model":"org-balanced","messages":[{"role":"user","content":"Hello"}],"max_tokens":64}'`}</pre></section>}
      <footer>{brand.name} · Development build · Synthetic pricing, real accounting</footer>
    </main>
  </div>;
}
