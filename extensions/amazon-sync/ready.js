// Non-order pages report sign-in/redirect status. The collector announces itself.
const path = location.pathname;
const page = /\/(?:ap\/(?:signin|cvf)|errors\/validateCaptcha)(?:\/|$)/i.test(path)
  ? 'auth'
  : /\/(?:gp\/(?:your-account|css)\/order-history|your-orders)(?:\/|$)/i.test(path)
    ? 'orders' : 'other';
if(page!=='orders')chrome.runtime.sendMessage({action:'collectorReady',page}).catch(()=>{});
