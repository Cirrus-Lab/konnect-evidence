"use strict";
(function () {
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const GATE_ICON = { approved: "✓", blocked: "!", rejected: "✕", not_applicable: "–" };
  let state = null, root = 0, selectedGate = null, pending = null, timer = null;

  // Build DOM nodes with text content only; record fields are never parsed as HTML.
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "width") el.style.width = v; // CSSOM, allowed by the CSP (inline style attributes are not)
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const label = (s) => String(s || "").replace(/_/g, " ");
  function when(iso) {
    if (!iso || !/^\d{4}-/.test(iso)) return iso || "";
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function remaining(iso) {
    const ms = new Date(iso) - Date.now();
    if (isNaN(ms)) return "";
    if (ms <= 0) return "expired";
    const m = Math.round(ms / 60000);
    return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min left` : `${m} min left`;
  }

  async function load() {
    try {
      const r = await fetch(`/api/state/${root}`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      state = await r.json();
      render();
      $("refresh").className = "refresh tick";
      setTimeout(() => ($("refresh").className = "refresh"), 600);
    } catch (e) {
      $("refresh").className = "refresh stale";
      $("design-line").textContent = "Cannot reach the console (" + e.message + ")";
    }
  }

  function render() {
    const id = state.identity;
    $("design-line").textContent = `${id.product_id || ""} · ${id.design_id} · ${id.board_id} · rev ${id.revision} · ${label(id.release_state)}`;
    const v = state.viewer;
    $("viewer").replaceChildren("Deciding as ", h("b", {}, v.actor), v.roles.length ? ` · ${v.roles.map(label).join(", ")}` : " · no roles");
    const lb = $("ledger-badge");
    lb.className = "pill " + (state.ledger.verified ? "ok" : "bad");
    lb.textContent = state.ledger.verified ? `Ledger verified · ${state.ledger.count}` : "Ledger broken";
    lb.title = state.ledger.problems.join("\n");
    renderQueue(); renderGates(); renderWindows(); renderLedger();
  }

  function scopeChips(w) {
    return h("div", { class: "chips" },
      (w.scope || []).map((s) => h("span", { class: "chip" }, s)),
      (w.files || []).map((f) => h("span", { class: "chip file" }, f)));
  }

  function renderQueue() {
    const q = state.windows.filter((w) => w.window_state === "requested");
    const v = state.viewer;
    $("queue").replaceChildren(...(q.length ? q.map((w) => {
      const self = w.requested_by === v.actor && !state.policy.self_approval;
      const blockedWhy = !v.can_decide ? `${v.actor} has no approver role (${state.policy.approver_roles.join(" or ")})`
        : self ? "You requested this window; another reviewer must decide it" : null;
      return h("article", { class: "qcard" },
        h("div", { class: "bar" }),
        h("div", { class: "body" },
          h("div", { class: "qhead" }, h("span", { class: "wid" }, w.id), h("span", { class: "state-tag requested" }, "awaiting decision")),
          h("div", { class: "reason" }, w.reason),
          scopeChips(w),
          h("div", { class: "meta" },
            h("span", {}, "Requested by ", h("b", {}, w.requested_by)),
            h("span", {}, when(w.timestamp)),
            h("span", {}, `${w.hours} h · up to ${w.max_calls} calls`),
            w.issue ? h("span", {}, "Issue ", w.issue) : null),
          blockedWhy ? h("div", { class: "note" }, blockedWhy) : null),
        h("div", { class: "actions" },
          h("button", { class: "btn primary", disabled: !!blockedWhy, onclick: () => openDecision(w, "approved") }, "Approve"),
          h("button", { class: "btn danger", disabled: !!blockedWhy, onclick: () => openDecision(w, "rejected") }, "Reject")));
    }) : [h("div", { class: "empty" }, "Nothing is waiting for you.")]));
  }

  function renderGates() {
    $("gates").replaceChildren(...state.gates.map((g) => h("button", {
      class: `gate g-${g.state}${selectedGate === g.gate ? " sel" : ""}`, title: g.next_action || "",
      onclick: () => { selectedGate = selectedGate === g.gate ? null : g.gate; renderGates(); },
    }, h("div", { class: "node" }, GATE_ICON[g.state] || "•"), h("div", { class: "gname" }, label(g.gate)), h("div", { class: "gstate" }, label(g.state)))));
    const d = $("gate-detail");
    const g = state.gates.find((x) => x.gate === selectedGate);
    d.hidden = !g;
    if (!g) return;
    d.replaceChildren(
      h("h3", {}, `${label(g.gate)} — ${label(g.state)}`),
      g.next_action ? h("div", { class: "note" }, "Next: ", g.next_action) : null,
      h("ul", { class: "checks" }, (g.checks || []).map((c) => h("li", {},
        h("span", { class: `res ${c.result === "not_applicable" ? "na" : c.result}` }, label(c.result)),
        h("span", {}, h("b", {}, label(c.check)), " — ", c.detail || "", c.next_action ? h("div", { class: "note" }, c.next_action) : null)))));
  }

  function lifecycle(w) {
    const s = w.window_state_effective;
    const steps = [["Requested", true]];
    if (s === "rejected") steps.push(["Rejected", "bad"]);
    else steps.push(["Approved", s !== "requested"]);
    steps.push(["In use", w.calls_used > 0 || s === "closed" ? true : s === "approved" ? "now" : false]);
    steps.push([s === "expired" ? "Expired" : "Closed", s === "closed" ? true : s === "expired" ? "bad" : false]);
    if (s === "requested") steps[1][1] = "now";
    return h("div", { class: "lifecycle" }, steps.map(([n, st]) =>
      h("div", { class: `step ${st === true ? "done" : st === "now" ? "now" : st === "bad" ? "bad" : ""}` }, h("div", { class: "pt" }), n)));
  }

  function renderWindows() {
    const ws = state.windows;
    $("windows").replaceChildren(...(ws.length ? ws.map((w) => {
      const s = w.window_state_effective;
      const pct = Math.min(100, Math.round((100 * w.calls_used) / Math.max(1, w.max_calls)));
      return h("article", { class: "wcard" },
        h("div", { class: "qhead" }, h("span", { class: "wid" }, w.id), h("span", { class: `state-tag ${s}` }, label(s))),
        lifecycle(w),
        h("div", { class: "reason" }, w.reason),
        scopeChips(w),
        h("div", { class: "budget" },
          h("div", {}, `${w.calls_used} / ${w.max_calls} calls` + (s === "approved" ? ` · ${remaining(w.expires_at)}` : "")),
          h("div", { class: "track" }, h("span", { width: `${pct}%` }))),
        h("div", { class: "meta" },
          h("span", {}, "By ", h("b", {}, w.requested_by)),
          w.approved_by ? h("span", {}, s === "rejected" ? "Rejected by " : "Approved by ", h("b", {}, w.approved_by)) : null,
          w.decided_at ? h("span", {}, when(w.decided_at)) : null),
        w.decision_note ? h("div", { class: "note" }, "“", w.decision_note, "”") : null,
        w.close_reason ? h("div", { class: "note" }, "Closed: ", w.close_reason) : null);
    }) : [h("div", { class: "empty" }, "No change windows yet.")]));
    const sel = $("ledger-window"), cur = sel.value;
    sel.replaceChildren(h("option", { value: "" }, "All windows"), ...ws.map((w) => h("option", { value: w.id }, w.id)));
    sel.value = ws.some((w) => w.id === cur) ? cur : "";
  }

  function renderLedger() {
    const wf = $("ledger-window").value, denyOnly = $("ledger-deny").checked;
    const es = state.ledger.entries.filter((e) => (!wf || e.window === wf) && (!denyOnly || e.decision === "deny"));
    $("ledger").replaceChildren(...(es.length ? es.map((e) => {
      const isAuth = e.phase === "authorize";
      const verdict = isAuth ? e.decision : e.status;
      const files = (e.changed_files || []).map((p) => p.split(/[\\/]/).pop());
      return h("li", { class: isAuth ? e.decision : "complete" },
        h("span", { class: "time" }, when(e.timestamp)),
        h("span", { class: `badge ${verdict}` }, verdict),
        h("span", { class: "tool" }, h("b", {}, e.tool), " ", h("span", { class: "sub" }, `${e.toolset || ""} · ${e.effect || ""} · ${e.phase}`),
          h("div", { class: "sub" }, isAuth ? e.reason || "" : files.length ? `changed: ${files.join(", ")}` : "no design file changed")),
        h("span", { class: "sub mono" }, e.window || "–"));
    }) : [h("div", { class: "empty" }, "No Konnect calls recorded yet.")]));
  }

  function openDecision(w, decision) {
    pending = { w, decision };
    const approve = decision === "approved";
    $("decide-title").textContent = `${approve ? "Approve" : "Reject"} ${w.id}`;
    $("decide-summary").replaceChildren(
      h("div", {}, w.reason),
      scopeChips(w),
      h("div", { class: "note" }, `Requested by ${w.requested_by} · ${w.hours} h · up to ${w.max_calls} calls`),
      approve ? h("div", { class: "note" }, "While active, Konnect may make design edits inside this scope; each call is recorded.") : null);
    $("decide-submit").textContent = approve ? "Approve" : "Reject";
    $("decide-submit").className = "btn " + (approve ? "primary" : "danger");
    $("note-hint").textContent = approve ? "(optional)" : "(required: why)";
    for (const f of ["decide-pin", "decide-confirm", "decide-note"]) $(f).value = "";
    $("decide-error").textContent = "";
    $("decide").showModal();
    $("decide-pin").focus();
  }

  $("decide-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const err = $("decide-error");
    const pin = $("decide-pin").value.trim(), confirm = $("decide-confirm").value.trim(), note = $("decide-note").value.trim();
    if (!/^\d{6}$/.test(pin)) { err.textContent = "Enter the 6-digit PIN from the console terminal."; return; }
    if (confirm !== pending.w.id) { err.textContent = `Type ${pending.w.id} exactly to confirm.`; return; }
    if (pending.decision === "rejected" && !note) { err.textContent = "Say why the window is rejected."; return; }
    $("decide-submit").disabled = true;
    try {
      const r = await fetch(`/api/windows/${root}/${encodeURIComponent(pending.w.id)}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
        body: JSON.stringify({ decision: pending.decision, pin, confirm_id: confirm, note }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { err.textContent = body.error || `Failed (${r.status})`; return; }
      $("decide").close();
      await load();
    } finally {
      $("decide-submit").disabled = false;
    }
  });
  for (const f of ["decide-pin", "decide-confirm", "decide-note"]) $(f).addEventListener("input", () => ($("decide-error").textContent = ""));
  $("decide-cancel").addEventListener("click", () => $("decide").close());
  $("root-select").addEventListener("change", (e) => { root = Number(e.target.value); selectedGate = null; load(); });
  $("ledger-window").addEventListener("change", renderLedger);
  $("ledger-deny").addEventListener("change", renderLedger);

  load();
  timer = setInterval(() => { if (!$("decide").open) load(); }, 3000);
})();
