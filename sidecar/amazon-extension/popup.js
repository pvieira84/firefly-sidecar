// popup.js
var $ = (id) => document.getElementById(id);
var saved = await chrome.storage.local.get(["settings", "status", "pending"]);
for (const key of ["url", "token"]) $(key).value = saved.settings?.[key] || "";
$("connection-settings").open = !saved.settings?.url;
$("daily").checked = Boolean(saved.settings?.daily);
$("status").textContent = saved.status || "Save the connection, then sync.";
function pendingInfo(pending) {
  $("pending-info").textContent = pending ? `${pending.orders.length} collected orders waiting to send to ${pending.url}. Stopping collection keeps these orders; Discard removes this browser\u2019s queued copy.` : "";
  $("retry").disabled = !pending;
  $("discard").disabled = !pending;
}
pendingInfo(saved.pending);
var localDay = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
var now = /* @__PURE__ */ new Date();
$("end").value = localDay(now);
now.setDate(now.getDate() - 14);
$("start").value = localDay(now);
async function run(fn) {
  try {
    await fn();
  } catch (e) {
    $("status").textContent = e.message;
  }
}
$("save").onclick = () => run(async () => {
  const url = new URL($("url").value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw Error("Use a plain http(s) sidecar URL, including its subpath.");
  if ($("token").value.length < 32) throw Error("Use a sync token of at least 32 characters.");
  if (!await chrome.permissions.request({ origins: [url.origin + "/*"] })) throw Error("Sidecar access was not granted.");
  await chrome.storage.local.set({ settings: { url: url.href.replace(/\/$/, ""), token: $("token").value, account: saved.settings?.account || "default", daily: $("daily").checked } });
  await chrome.runtime.sendMessage({ action: "configure" });
  $("status").textContent = "Saved. Sign in to Amazon.es before syncing.";
});
for (const [id, action] of [["sync", "sync"], ["retry", "retry"], ["stop", "stop"], ["discard", "discard"]]) $(id).onclick = () => run(async () => {
  const result = await chrome.runtime.sendMessage({ action, start: $("start").value, end: $("end").value });
  if (!result.success) throw Error(result.error);
  const current = await chrome.storage.local.get(["status", "pending"]);
  $("status").textContent = current.status || "Request accepted.";
  pendingInfo(current.pending);
});
chrome.storage.onChanged.addListener((changes) => {
  if (changes.status) $("status").textContent = changes.status.newValue;
  if (changes.pending) pendingInfo(changes.pending.newValue);
});
