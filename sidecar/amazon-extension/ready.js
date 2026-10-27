// ready.js
var path = location.pathname;
var page = /\/(?:ap\/(?:signin|cvf)|errors\/validateCaptcha)(?:\/|$)/i.test(path) ? "auth" : /\/(?:gp\/(?:your-account|css)\/order-history|your-orders)(?:\/|$)/i.test(path) ? "orders" : "other";
if (page !== "orders") chrome.runtime.sendMessage({ action: "collectorReady", page }).catch(() => {
});
