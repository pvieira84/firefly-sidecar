var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __commonJS = (cb, mod) => function __require() {
  try {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  } catch (e) {
    throw mod = 0, e;
  }
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/webextension-polyfill/dist/browser-polyfill.js
var require_browser_polyfill = __commonJS({
  "node_modules/webextension-polyfill/dist/browser-polyfill.js"(exports, module) {
    (function(global, factory) {
      if (typeof define === "function" && define.amd) {
        define("webextension-polyfill", ["module"], factory);
      } else if (typeof exports !== "undefined") {
        factory(module);
      } else {
        var mod = {
          exports: {}
        };
        factory(mod);
        global.browser = mod.exports;
      }
    })(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : exports, function(module2) {
      "use strict";
      if (!(globalThis.chrome && globalThis.chrome.runtime && globalThis.chrome.runtime.id)) {
        throw new Error("This script should only be loaded in a browser extension.");
      }
      if (!(globalThis.browser && globalThis.browser.runtime && globalThis.browser.runtime.id)) {
        const CHROME_SEND_MESSAGE_CALLBACK_NO_RESPONSE_MESSAGE = "The message port closed before a response was received.";
        const wrapAPIs = (extensionAPIs) => {
          const apiMetadata = {
            "alarms": {
              "clear": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "clearAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "get": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "getAll": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "bookmarks": {
              "create": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "get": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getChildren": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getRecent": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getSubTree": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getTree": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "move": {
                "minArgs": 2,
                "maxArgs": 2
              },
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeTree": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "search": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "update": {
                "minArgs": 2,
                "maxArgs": 2
              }
            },
            "browserAction": {
              "disable": {
                "minArgs": 0,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "enable": {
                "minArgs": 0,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "getBadgeBackgroundColor": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getBadgeText": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getPopup": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getTitle": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "openPopup": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "setBadgeBackgroundColor": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "setBadgeText": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "setIcon": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "setPopup": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "setTitle": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              }
            },
            "browsingData": {
              "remove": {
                "minArgs": 2,
                "maxArgs": 2
              },
              "removeCache": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeCookies": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeDownloads": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeFormData": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeHistory": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeLocalStorage": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removePasswords": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removePluginData": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "settings": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "commands": {
              "getAll": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "contextMenus": {
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "update": {
                "minArgs": 2,
                "maxArgs": 2
              }
            },
            "cookies": {
              "get": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getAll": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getAllCookieStores": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "set": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "devtools": {
              "inspectedWindow": {
                "eval": {
                  "minArgs": 1,
                  "maxArgs": 2,
                  "singleCallbackArg": false
                }
              },
              "panels": {
                "create": {
                  "minArgs": 3,
                  "maxArgs": 3,
                  "singleCallbackArg": true
                },
                "elements": {
                  "createSidebarPane": {
                    "minArgs": 1,
                    "maxArgs": 1
                  }
                }
              }
            },
            "downloads": {
              "cancel": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "download": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "erase": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getFileIcon": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "open": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "pause": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeFile": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "resume": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "search": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "show": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              }
            },
            "extension": {
              "isAllowedFileSchemeAccess": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "isAllowedIncognitoAccess": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "history": {
              "addUrl": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "deleteAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "deleteRange": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "deleteUrl": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getVisits": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "search": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "i18n": {
              "detectLanguage": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getAcceptLanguages": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "identity": {
              "launchWebAuthFlow": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "idle": {
              "queryState": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "management": {
              "get": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "getSelf": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "setEnabled": {
                "minArgs": 2,
                "maxArgs": 2
              },
              "uninstallSelf": {
                "minArgs": 0,
                "maxArgs": 1
              }
            },
            "notifications": {
              "clear": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "create": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "getAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "getPermissionLevel": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "update": {
                "minArgs": 2,
                "maxArgs": 2
              }
            },
            "pageAction": {
              "getPopup": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getTitle": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "hide": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "setIcon": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "setPopup": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "setTitle": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              },
              "show": {
                "minArgs": 1,
                "maxArgs": 1,
                "fallbackToNoCallback": true
              }
            },
            "permissions": {
              "contains": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getAll": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "request": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "runtime": {
              "getBackgroundPage": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "getPlatformInfo": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "openOptionsPage": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "requestUpdateCheck": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "sendMessage": {
                "minArgs": 1,
                "maxArgs": 3
              },
              "sendNativeMessage": {
                "minArgs": 2,
                "maxArgs": 2
              },
              "setUninstallURL": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "sessions": {
              "getDevices": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "getRecentlyClosed": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "restore": {
                "minArgs": 0,
                "maxArgs": 1
              }
            },
            "storage": {
              "local": {
                "clear": {
                  "minArgs": 0,
                  "maxArgs": 0
                },
                "get": {
                  "minArgs": 0,
                  "maxArgs": 1
                },
                "getBytesInUse": {
                  "minArgs": 0,
                  "maxArgs": 1
                },
                "remove": {
                  "minArgs": 1,
                  "maxArgs": 1
                },
                "set": {
                  "minArgs": 1,
                  "maxArgs": 1
                }
              },
              "managed": {
                "get": {
                  "minArgs": 0,
                  "maxArgs": 1
                },
                "getBytesInUse": {
                  "minArgs": 0,
                  "maxArgs": 1
                }
              },
              "sync": {
                "clear": {
                  "minArgs": 0,
                  "maxArgs": 0
                },
                "get": {
                  "minArgs": 0,
                  "maxArgs": 1
                },
                "getBytesInUse": {
                  "minArgs": 0,
                  "maxArgs": 1
                },
                "remove": {
                  "minArgs": 1,
                  "maxArgs": 1
                },
                "set": {
                  "minArgs": 1,
                  "maxArgs": 1
                }
              }
            },
            "tabs": {
              "captureVisibleTab": {
                "minArgs": 0,
                "maxArgs": 2
              },
              "create": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "detectLanguage": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "discard": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "duplicate": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "executeScript": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "get": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getCurrent": {
                "minArgs": 0,
                "maxArgs": 0
              },
              "getZoom": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "getZoomSettings": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "goBack": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "goForward": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "highlight": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "insertCSS": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "move": {
                "minArgs": 2,
                "maxArgs": 2
              },
              "query": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "reload": {
                "minArgs": 0,
                "maxArgs": 2
              },
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "removeCSS": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "sendMessage": {
                "minArgs": 2,
                "maxArgs": 3
              },
              "setZoom": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "setZoomSettings": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "update": {
                "minArgs": 1,
                "maxArgs": 2
              }
            },
            "topSites": {
              "get": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "webNavigation": {
              "getAllFrames": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "getFrame": {
                "minArgs": 1,
                "maxArgs": 1
              }
            },
            "webRequest": {
              "handlerBehaviorChanged": {
                "minArgs": 0,
                "maxArgs": 0
              }
            },
            "windows": {
              "create": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "get": {
                "minArgs": 1,
                "maxArgs": 2
              },
              "getAll": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "getCurrent": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "getLastFocused": {
                "minArgs": 0,
                "maxArgs": 1
              },
              "remove": {
                "minArgs": 1,
                "maxArgs": 1
              },
              "update": {
                "minArgs": 2,
                "maxArgs": 2
              }
            }
          };
          if (Object.keys(apiMetadata).length === 0) {
            throw new Error("api-metadata.json has not been included in browser-polyfill");
          }
          class DefaultWeakMap extends WeakMap {
            constructor(createItem, items = void 0) {
              super(items);
              this.createItem = createItem;
            }
            get(key) {
              if (!this.has(key)) {
                this.set(key, this.createItem(key));
              }
              return super.get(key);
            }
          }
          const isThenable = (value) => {
            return value && typeof value === "object" && typeof value.then === "function";
          };
          const makeCallback = (promise, metadata) => {
            return (...callbackArgs) => {
              if (extensionAPIs.runtime.lastError) {
                promise.reject(new Error(extensionAPIs.runtime.lastError.message));
              } else if (metadata.singleCallbackArg || callbackArgs.length <= 1 && metadata.singleCallbackArg !== false) {
                promise.resolve(callbackArgs[0]);
              } else {
                promise.resolve(callbackArgs);
              }
            };
          };
          const pluralizeArguments = (numArgs) => numArgs == 1 ? "argument" : "arguments";
          const wrapAsyncFunction = (name, metadata) => {
            return function asyncFunctionWrapper(target, ...args) {
              if (args.length < metadata.minArgs) {
                throw new Error(`Expected at least ${metadata.minArgs} ${pluralizeArguments(metadata.minArgs)} for ${name}(), got ${args.length}`);
              }
              if (args.length > metadata.maxArgs) {
                throw new Error(`Expected at most ${metadata.maxArgs} ${pluralizeArguments(metadata.maxArgs)} for ${name}(), got ${args.length}`);
              }
              return new Promise((resolve, reject) => {
                if (metadata.fallbackToNoCallback) {
                  try {
                    target[name](...args, makeCallback({
                      resolve,
                      reject
                    }, metadata));
                  } catch (cbError) {
                    console.warn(`${name} API method doesn't seem to support the callback parameter, falling back to call it without a callback: `, cbError);
                    target[name](...args);
                    metadata.fallbackToNoCallback = false;
                    metadata.noCallback = true;
                    resolve();
                  }
                } else if (metadata.noCallback) {
                  target[name](...args);
                  resolve();
                } else {
                  target[name](...args, makeCallback({
                    resolve,
                    reject
                  }, metadata));
                }
              });
            };
          };
          const wrapMethod = (target, method, wrapper) => {
            return new Proxy(method, {
              apply(targetMethod, thisObj, args) {
                return wrapper.call(thisObj, target, ...args);
              }
            });
          };
          let hasOwnProperty = Function.call.bind(Object.prototype.hasOwnProperty);
          const wrapObject = (target, wrappers = {}, metadata = {}) => {
            let cache = /* @__PURE__ */ Object.create(null);
            let handlers = {
              has(proxyTarget2, prop) {
                return prop in target || prop in cache;
              },
              get(proxyTarget2, prop, receiver) {
                if (prop in cache) {
                  return cache[prop];
                }
                if (!(prop in target)) {
                  return void 0;
                }
                let value = target[prop];
                if (typeof value === "function") {
                  if (typeof wrappers[prop] === "function") {
                    value = wrapMethod(target, target[prop], wrappers[prop]);
                  } else if (hasOwnProperty(metadata, prop)) {
                    let wrapper = wrapAsyncFunction(prop, metadata[prop]);
                    value = wrapMethod(target, target[prop], wrapper);
                  } else {
                    value = value.bind(target);
                  }
                } else if (typeof value === "object" && value !== null && (hasOwnProperty(wrappers, prop) || hasOwnProperty(metadata, prop))) {
                  value = wrapObject(value, wrappers[prop], metadata[prop]);
                } else if (hasOwnProperty(metadata, "*")) {
                  value = wrapObject(value, wrappers[prop], metadata["*"]);
                } else {
                  Object.defineProperty(cache, prop, {
                    configurable: true,
                    enumerable: true,
                    get() {
                      return target[prop];
                    },
                    set(value2) {
                      target[prop] = value2;
                    }
                  });
                  return value;
                }
                cache[prop] = value;
                return value;
              },
              set(proxyTarget2, prop, value, receiver) {
                if (prop in cache) {
                  cache[prop] = value;
                } else {
                  target[prop] = value;
                }
                return true;
              },
              defineProperty(proxyTarget2, prop, desc) {
                return Reflect.defineProperty(cache, prop, desc);
              },
              deleteProperty(proxyTarget2, prop) {
                return Reflect.deleteProperty(cache, prop);
              }
            };
            let proxyTarget = Object.create(target);
            return new Proxy(proxyTarget, handlers);
          };
          const wrapEvent = (wrapperMap) => ({
            addListener(target, listener, ...args) {
              target.addListener(wrapperMap.get(listener), ...args);
            },
            hasListener(target, listener) {
              return target.hasListener(wrapperMap.get(listener));
            },
            removeListener(target, listener) {
              target.removeListener(wrapperMap.get(listener));
            }
          });
          const onRequestFinishedWrappers = new DefaultWeakMap((listener) => {
            if (typeof listener !== "function") {
              return listener;
            }
            return function onRequestFinished(req) {
              const wrappedReq = wrapObject(req, {}, {
                getContent: {
                  minArgs: 0,
                  maxArgs: 0
                }
              });
              listener(wrappedReq);
            };
          });
          const onMessageWrappers = new DefaultWeakMap((listener) => {
            if (typeof listener !== "function") {
              return listener;
            }
            return function onMessage(message, sender, sendResponse) {
              let didCallSendResponse = false;
              let wrappedSendResponse;
              let sendResponsePromise = new Promise((resolve) => {
                wrappedSendResponse = function(response) {
                  didCallSendResponse = true;
                  resolve(response);
                };
              });
              let result;
              try {
                result = listener(message, sender, wrappedSendResponse);
              } catch (err) {
                result = Promise.reject(err);
              }
              const isResultThenable = result !== true && isThenable(result);
              if (result !== true && !isResultThenable && !didCallSendResponse) {
                return false;
              }
              const sendPromisedResult = (promise) => {
                promise.then((msg) => {
                  sendResponse(msg);
                }, (error) => {
                  let message2;
                  if (error && (error instanceof Error || typeof error.message === "string")) {
                    message2 = error.message;
                  } else {
                    message2 = "An unexpected error occurred";
                  }
                  sendResponse({
                    __mozWebExtensionPolyfillReject__: true,
                    message: message2
                  });
                }).catch((err) => {
                  console.error("Failed to send onMessage rejected reply", err);
                });
              };
              if (isResultThenable) {
                sendPromisedResult(result);
              } else {
                sendPromisedResult(sendResponsePromise);
              }
              return true;
            };
          });
          const wrappedSendMessageCallback = ({
            reject,
            resolve
          }, reply) => {
            if (extensionAPIs.runtime.lastError) {
              if (extensionAPIs.runtime.lastError.message === CHROME_SEND_MESSAGE_CALLBACK_NO_RESPONSE_MESSAGE) {
                resolve();
              } else {
                reject(new Error(extensionAPIs.runtime.lastError.message));
              }
            } else if (reply && reply.__mozWebExtensionPolyfillReject__) {
              reject(new Error(reply.message));
            } else {
              resolve(reply);
            }
          };
          const wrappedSendMessage = (name, metadata, apiNamespaceObj, ...args) => {
            if (args.length < metadata.minArgs) {
              throw new Error(`Expected at least ${metadata.minArgs} ${pluralizeArguments(metadata.minArgs)} for ${name}(), got ${args.length}`);
            }
            if (args.length > metadata.maxArgs) {
              throw new Error(`Expected at most ${metadata.maxArgs} ${pluralizeArguments(metadata.maxArgs)} for ${name}(), got ${args.length}`);
            }
            return new Promise((resolve, reject) => {
              const wrappedCb = wrappedSendMessageCallback.bind(null, {
                resolve,
                reject
              });
              args.push(wrappedCb);
              apiNamespaceObj.sendMessage(...args);
            });
          };
          const staticWrappers = {
            devtools: {
              network: {
                onRequestFinished: wrapEvent(onRequestFinishedWrappers)
              }
            },
            runtime: {
              onMessage: wrapEvent(onMessageWrappers),
              onMessageExternal: wrapEvent(onMessageWrappers),
              sendMessage: wrappedSendMessage.bind(null, "sendMessage", {
                minArgs: 1,
                maxArgs: 3
              })
            },
            tabs: {
              sendMessage: wrappedSendMessage.bind(null, "sendMessage", {
                minArgs: 2,
                maxArgs: 3
              })
            }
          };
          const settingMetadata = {
            clear: {
              minArgs: 1,
              maxArgs: 1
            },
            get: {
              minArgs: 1,
              maxArgs: 1
            },
            set: {
              minArgs: 1,
              maxArgs: 1
            }
          };
          apiMetadata.privacy = {
            network: {
              "*": settingMetadata
            },
            services: {
              "*": settingMetadata
            },
            websites: {
              "*": settingMetadata
            }
          };
          return wrapObject(extensionAPIs, staticWrappers, apiMetadata);
        };
        module2.exports = wrapAPIs(chrome);
      } else {
        module2.exports = globalThis.browser;
      }
    });
  }
});

// vendor/src/content/content.ts
var import_webextension_polyfill = __toESM(require_browser_polyfill(), 1);

// vendor/src/utils/dateUtils.ts
var germanMonths = {
  januar: 1,
  februar: 2,
  m\u00E4rz: 3,
  april: 4,
  mai: 5,
  juni: 6,
  juli: 7,
  august: 8,
  september: 9,
  oktober: 10,
  november: 11,
  dezember: 12
};
var englishMonths = {
  january: 1,
  february: 2,
  march: 3,
  april: 4,
  may: 5,
  june: 6,
  july: 7,
  august: 8,
  september: 9,
  october: 10,
  november: 11,
  december: 12
};
var frenchMonths = {
  janvier: 1,
  f\u00E9vrier: 2,
  fevrier: 2,
  mars: 3,
  avril: 4,
  mai: 5,
  juin: 6,
  juillet: 7,
  ao\u00FBt: 8,
  aout: 8,
  septembre: 9,
  octobre: 10,
  novembre: 11,
  d\u00E9cembre: 12,
  decembre: 12
};
var swedishMonths = {
  januari: 1,
  februari: 2,
  mars: 3,
  april: 4,
  maj: 5,
  juni: 6,
  juli: 7,
  augusti: 8,
  september: 9,
  oktober: 10,
  november: 11,
  december: 12
};
var spanishMonths = {
  enero: 1,
  febrero: 2,
  marzo: 3,
  abril: 4,
  mayo: 5,
  junio: 6,
  julio: 7,
  agosto: 8,
  septiembre: 9,
  octubre: 10,
  noviembre: 11,
  diciembre: 12
};
var italianMonths = {
  gennaio: 1,
  febbraio: 2,
  marzo: 3,
  aprile: 4,
  maggio: 5,
  giugno: 6,
  luglio: 7,
  agosto: 8,
  settembre: 9,
  ottobre: 10,
  novembre: 11,
  dicembre: 12
};
var allMonths = {
  ...germanMonths,
  ...englishMonths,
  ...frenchMonths,
  ...swedishMonths,
  ...spanishMonths,
  ...italianMonths
};
var germanMonthNames = "Januar|Februar|M\xE4rz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember";
var frenchMonthNames = "janvier|f\xE9vrier|fevrier|mars|avril|mai|juin|juillet|ao\xFBt|aout|septembre|octobre|novembre|d\xE9cembre|decembre";
var englishMonthNames = "January|February|March|April|May|June|July|August|September|October|November|December";
var swedishMonthNames = "januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december";
var spanishMonthNames = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre";
var italianMonthNames = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre";
var japaneseDatePattern = "\\d{4}\\s*\u5E74\\s*\\d{1,2}\\s*\u6708\\s*\\d{1,2}\\s*\u65E5";
var orderDatePatterns = [
  new RegExp(
    `(?:\u6CE8\u6587\u65E5|\u6CE8\u6587\u78BA\u5B9A\u65E5)[:\uFF1A\\s]*(${japaneseDatePattern}|\\d{4}/\\d{1,2}/\\d{1,2})`,
    "u"
  ),
  new RegExp(`(${japaneseDatePattern})`, "u"),
  new RegExp(
    `(?:Bestellt am|Bestellung aufgegeben am)\\s+(\\d{1,2}\\.?\\s*(?:${germanMonthNames})\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}\\.?\\s*(?:${germanMonthNames})\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Command\xE9 le|Commande pass\xE9e le)\\s+(\\d{1,2}(?:er)?\\s*(?:${frenchMonthNames})\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}(?:er)?\\s*(?:${frenchMonthNames})\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Best\xE4lld den|Best\xE4llning gjord den)\\s+(\\d{1,2}\\.?\\s*(?:${swedishMonthNames})\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}\\.?\\s*(?:${swedishMonthNames})\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Pedido realizado|Suscripci\xF3n cobrada el|Suscripcion cobrada el)\\s+(\\d{1,2}\\s+de\\s+(?:${spanishMonthNames})\\s+de\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}\\s+de\\s+(?:${spanishMonthNames})\\s+de\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Ordine effettuato il|Ordine effettuato)\\s+(\\d{1,2}\\s*(?:${italianMonthNames})\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}\\s*(?:${italianMonthNames})\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Order placed|Ordered on)\\s+((?:${englishMonthNames})\\s+\\d{1,2},?\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b((?:${englishMonthNames})\\s+\\d{1,2},?\\s+\\d{4})\\b`, "iu"),
  new RegExp(
    `(?:Order placed|Order placed on|Ordered on)\\s+(\\d{1,2}(?:st|nd|rd|th)?\\s*(?:${englishMonthNames})\\s+\\d{4})\\b`,
    "iu"
  ),
  new RegExp(`\\b(\\d{1,2}(?:st|nd|rd|th)?\\s*(?:${englishMonthNames})\\s+\\d{4})\\b`, "iu")
];
function getDateCandidates(orderText) {
  const normalized = orderText.replace(/\u00a0/g, " ").trim();
  if (!normalized) return [];
  const byLine = normalized.split(/\r?\n+/).map((line) => line.replace(/\s+/g, " ").trim()).filter(Boolean);
  if (byLine.length > 1) return byLine;
  const byChunk = normalized.split(/\s{2,}|\s[|]\s|\s[-–—]\s/).map((chunk) => chunk.replace(/\s+/g, " ").trim()).filter(Boolean);
  return byChunk.length > 0 ? byChunk : [normalized.replace(/\s+/g, " ").trim()];
}
function toIsoDate(year, month, day) {
  if (year < 2e3 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
function parseDate(dateText) {
  if (!dateText) return null;
  const cleanText = dateText.trim().toLowerCase();
  const japaneseMatch = cleanText.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/u) || cleanText.match(/(?<!\d)(\d{4})\/(\d{1,2})\/(\d{1,2})(?!\d)/);
  if (japaneseMatch) {
    return toIsoDate(
      parseInt(japaneseMatch[1] || "0", 10),
      parseInt(japaneseMatch[2] || "0", 10),
      parseInt(japaneseMatch[3] || "0", 10)
    );
  }
  const spanishMonthPattern = new RegExp(`\\b(?:${spanishMonthNames})\\b`, "iu");
  const normalizedText = spanishMonthPattern.test(cleanText) ? cleanText.replace(/\bde\b/gi, " ").replace(/\s+/g, " ").trim() : cleanText;
  const dayMonthYearMatch = normalizedText.match(
    /(\d{1,2})(?:er|st|nd|rd|th)?\.?\s*([\p{L}]+)\s*(\d{4})/iu
  );
  if (dayMonthYearMatch) {
    const day = parseInt(dayMonthYearMatch[1] || "0", 10);
    const monthName = (dayMonthYearMatch[2] || "").toLowerCase();
    const year = parseInt(dayMonthYearMatch[3] || "0", 10);
    if (year >= 2e3 && year <= 2100 && allMonths[monthName]) {
      const month = allMonths[monthName];
      return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }
  }
  const englishMatch = normalizedText.match(/([a-z]+)\s+(\d{1,2}),?\s*(\d{4})/i);
  if (englishMatch) {
    const monthName = (englishMatch[1] || "").toLowerCase();
    const day = parseInt(englishMatch[2] || "0", 10);
    const year = parseInt(englishMatch[3] || "0", 10);
    if (year >= 2e3 && year <= 2100 && allMonths[monthName]) {
      const month = allMonths[monthName];
      return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }
  }
  return null;
}
function parseOrderDate(orderText) {
  if (!orderText) return "";
  const candidates = getDateCandidates(orderText);
  for (const candidate of candidates) {
    for (const pattern of orderDatePatterns) {
      const match = candidate.match(pattern);
      if (match?.[1]) {
        const parsedDate = parseDate(match[1]);
        if (parsedDate && parsedDate.startsWith("20")) {
          return parsedDate;
        }
      }
    }
  }
  return "";
}
function parseOrderDateFromRows(rows) {
  for (const row of rows) {
    const parsed = parseDate(row.value);
    if (parsed) return parsed;
  }
  return "";
}
function extractOrderYear(value) {
  if (!value) return null;
  const yearMatch = value.match(/year-?(20\d{2})/i) || value.match(/\b(20\d{2})\b/);
  return yearMatch?.[1] || null;
}
function filterYearsByDateRange(years, startDate, endDate) {
  if (!startDate || !endDate) {
    return years;
  }
  const startYear = new Date(startDate).getFullYear();
  const endYear = new Date(endDate).getFullYear();
  return years.filter((year) => {
    const yearNum = parseInt(year, 10);
    return yearNum >= startYear && yearNum <= endYear;
  });
}

// vendor/src/utils/priceUtils.ts
function parsePrice(priceStr) {
  if (!priceStr) return 0;
  let cleaned = priceStr.trim();
  if (cleaned.includes(",") && cleaned.includes(".")) {
    const lastComma = cleaned.lastIndexOf(",");
    const lastPeriod = cleaned.lastIndexOf(".");
    if (lastComma > lastPeriod) {
      cleaned = cleaned.replace(/\./g, "").replace(",", ".");
    } else {
      cleaned = cleaned.replace(/,/g, "");
    }
  } else if (cleaned.includes(",")) {
    const parts = cleaned.split(",");
    if (parts.length === 2 && parts[1] && parts[1].length <= 2) {
      cleaned = cleaned.replace(",", ".");
    } else {
      cleaned = cleaned.replace(/,/g, "");
    }
  }
  const amount = parseFloat(cleaned);
  return isNaN(amount) ? 0 : amount;
}
var CURRENCY_TOKEN = "(?:\\b(?:EUR|GBP|USD|SEK|AUD|CAD|MXN|BRL|JPY|INR|KR|AED)\\b|\u20AC|\xA3|\\$|R\\$|\xA5|\uFFE5|\u20B9)";
var YEN_SUFFIX = "\u5186";
var ZERO_DECIMAL_CURRENCIES = /* @__PURE__ */ new Set(["JPY"]);
function getAmountPattern(currency) {
  return ZERO_DECIMAL_CURRENCIES.has(currency) ? "(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?![0-9,%\uFF05])" : "[0-9]+[.,][0-9]{2}";
}
var DOMAIN_CURRENCY_MAP = {
  "amazon.ae": "AED",
  "amazon.com": "USD",
  "amazon.com.au": "AUD",
  "amazon.ca": "CAD",
  "amazon.com.mx": "MXN",
  "amazon.com.br": "BRL",
  "amazon.co.jp": "JPY",
  "amazon.in": "INR",
  "amazon.co.uk": "GBP",
  "amazon.se": "SEK",
  "amazon.de": "EUR",
  "amazon.fr": "EUR",
  "amazon.it": "EUR",
  "amazon.es": "EUR",
  "amazon.com.be": "EUR"
};
function getCurrencyForDomain(hostname) {
  const normalized = hostname.toLowerCase();
  for (const [domain, currency] of Object.entries(DOMAIN_CURRENCY_MAP)) {
    if (normalized === domain || normalized.endsWith(`.${domain}`)) {
      return currency;
    }
  }
  return null;
}
function detectCurrency(text, hostname) {
  if (text.includes("\u20AC") || text.includes("EUR")) {
    return "EUR";
  } else if (text.includes("AED")) {
    return "AED";
  } else if (text.includes("\xA3") || text.includes("GBP")) {
    return "GBP";
  } else if (text.includes("R$") || text.includes("BRL")) {
    return "BRL";
  } else if (text.includes("\xA5") || text.includes("\uFFE5") || text.includes(YEN_SUFFIX) || text.includes("JPY")) {
    return "JPY";
  } else if (text.includes("\u20B9") || text.includes("INR")) {
    return "INR";
  } else if (text.includes("AUD")) {
    return "AUD";
  } else if (text.includes("CAD")) {
    return "CAD";
  } else if (text.includes("MXN")) {
    return "MXN";
  } else if (text.includes("USD")) {
    return "USD";
  } else if (text.includes("$")) {
    if (hostname) {
      const domainCurrency = getCurrencyForDomain(hostname);
      if (domainCurrency) {
        return domainCurrency;
      }
    }
    return "USD";
  } else if (/(?:\d[\d.,]*\s*kr|kr\s*\d[\d.,]*|SEK)/i.test(text)) {
    return "SEK";
  }
  if (hostname) {
    const domainCurrency = getCurrencyForDomain(hostname);
    if (domainCurrency) return domainCurrency;
  }
  return "EUR";
}
function parseCurrencyAmount(text) {
  return parsePrice(
    text.replace(new RegExp(CURRENCY_TOKEN, "gi"), "").replace(new RegExp(YEN_SUFFIX, "g"), "").trim()
  );
}
function extractPriceFromText(text, hostname) {
  const CT = CURRENCY_TOKEN;
  const pricePatterns = [
    // Labeled totals with optional currency prefix/suffix (e.g. "Total: $12.99")
    new RegExp(
      `(?:Summe|Gesamtsumme|Gesamt|Total|Totale|Totalt|Summa|\u3054\u8ACB\u6C42\u984D|\u5408\u8A08)[:\uFF1A\\s]*${CT}?\\s*([0-9][0-9.,]*)\\s*(?:${CT}|${YEN_SUFFIX})?`,
      "gi"
    ),
    // Currency-prefixed amounts (e.g. "$ 29.99", "EUR 12,99")
    new RegExp(`${CT}\\s*([0-9][0-9.,]*)`, "gi"),
    // Currency-suffixed amounts (e.g. "199,00 kr", "12.99 EUR")
    new RegExp(`([0-9]+[.,][0-9]{2})\\s*${CT}`, "gi"),
    // Yen-suffixed amounts without decimals (e.g. "3,480円")
    new RegExp(`([0-9][0-9,]*)\\s*${YEN_SUFFIX}`, "g")
  ];
  for (const pattern of pricePatterns) {
    for (const match of text.matchAll(pattern)) {
      if (match[1]) {
        const amount = parsePrice(match[1]);
        if (amount > 0) {
          return {
            amount,
            currency: detectCurrency(text, hostname)
          };
        }
      }
    }
  }
  return null;
}
var TOTAL_LABEL_PATTERN = /^(?:(?:total|totale|summe|gesamt|totalt|summa)\b|合計|注文合計|ご請求額)/i;
function extractTotalFromRows(rows, hostname) {
  for (const row of rows) {
    if (TOTAL_LABEL_PATTERN.test(row.label.trim())) {
      const result = extractPriceFromText(`${row.label} ${row.value}`, hostname);
      if (result) return result;
    }
  }
  return null;
}
var GIFT_CARD_LABEL_PATTERN = /(gift\s*card|geschenkgutschein|ch[eè]que[\s-]?cadeau|carte[\s-]?cadeau|presentkort|tarjeta\s*(de\s*)?regalo|cheque\s*regalo|buono\s*regalo|ギフトカード|ギフト券)/i;
var REFUND_TOTAL_LABEL_PATTERN = /(total\s*refund|r[uü]ckerstattungsbetrag|montant\s*rembours[eé]|[aå]terbetalt\s*belopp|importe\s*reembolsado|totale\s*rimborso|返金合計|返金額|返金総額)/i;
function summarizePaymentRows(rows) {
  const chargeRows = rows.filter((row) => !REFUND_TOTAL_LABEL_PATTERN.test(row.label));
  if (chargeRows.length === 0) {
    return { chargedAmount: null, giftCardAmount: 0 };
  }
  const chargedAmount = chargeRows[chargeRows.length - 1]?.amount ?? null;
  const giftCardAmount = chargeRows.filter((row) => row.amount < 0 && GIFT_CARD_LABEL_PATTERN.test(row.label)).reduce((sum, row) => sum + Math.abs(row.amount), 0);
  return { chargedAmount, giftCardAmount: Math.round(giftCardAmount * 100) / 100 };
}

// vendor/src/utils/orderUtils.ts
function isAdvertisementOrder(order) {
  if (!order.orderDate) {
    const adPatterns = [
      /amazon\s*visa/i,
      /barclays\s*finanzierung/i,
      /amazon\s*business.*card/i,
      /kreditkarte/i,
      /finanzierung/i,
      /prime.*card/i,
      /amazon.*amex/i
    ];
    const hasAdItem = order.items.some(
      (item) => adPatterns.some((pattern) => pattern.test(item.title))
    );
    if (hasAdItem) {
      return true;
    }
    if (!order.orderStatus && !order.detailsUrl) {
      const allPricesZero = order.items.every((item) => item.price === 0);
      if (allPricesZero && order.items.length > 5) {
        return true;
      }
    }
  }
  return false;
}
var ORDER_ID_PATTERN = "(?:\\d{3}|D\\d{2})-\\d{7}-\\d{7}";
function extractOrderId(text) {
  const orderIdMatch = text.match(new RegExp(ORDER_ID_PATTERN));
  return orderIdMatch?.[0] || null;
}
function extractOrderIdFromUrl(url) {
  const urlMatch = url.match(new RegExp(`orderI[Dd]=(${ORDER_ID_PATTERN})`, "i"));
  return urlMatch?.[1] || null;
}

// vendor/src/utils/statusUtils.ts
var STATUS_TOKEN = "[\\p{L}\\d.,'\u2019:/()\\-]";
var localeStatusConfigs = [
  {
    locale: "de",
    keywords: ["Zugestellt", "Geliefert", "Storniert"]
  },
  {
    locale: "en",
    keywords: [
      "Delivered",
      "Likely delivered",
      "Arriving",
      "Shipped",
      "Cancelled",
      "Return complete",
      "Return started",
      "Returned",
      "Refunded"
    ]
  },
  {
    locale: "fr",
    keywords: [
      "Livr\xE9",
      "Livre",
      "Probablement livr\xE9",
      "Probablement livre",
      "Remis",
      "Arrive",
      "Arriv\xE9",
      "Exp\xE9di\xE9",
      "Expedie",
      "En cours",
      "Annul\xE9",
      "Annule",
      "Retour termin\xE9",
      "Retour termine",
      "Retourn\xE9",
      "Retourne",
      "Rembours\xE9",
      "Rembourse"
    ]
  },
  {
    locale: "sv",
    keywords: [
      "Levererad",
      "Levererat",
      "Troligen levererad",
      "Troligen levererat",
      "Skickad",
      "Skickat",
      "Avbruten",
      "Avbrutet",
      "Returnerad",
      "Returnerat",
      "\xC5terbetalad",
      "\xC5terbetalat",
      "Aterbetalad",
      "Aterbetalat",
      "Retur slutf\xF6rd",
      "Retur slutf\xF6rt",
      "Retur slutford",
      "Retur slutfort",
      "Retur p\xE5b\xF6rjad",
      "Retur p\xE5b\xF6rjat",
      "Retur paborjad",
      "Retur paborjat",
      "Anl\xE4nder",
      "Anlander"
    ]
  },
  {
    locale: "es",
    keywords: [
      "Entregado",
      "Entregada",
      "Probablemente entregado",
      "Probablemente entregada",
      "Enviado",
      "Enviada",
      "En camino",
      "Llegando",
      "Cancelado",
      "Cancelada",
      "Devuelto",
      "Devuelta",
      "Devoluci\xF3n completada",
      "Devoluci\xF3n finalizada",
      "Devolucion completada",
      "Devolucion finalizada",
      "Devoluci\xF3n iniciada",
      "Devolucion iniciada",
      "Devoluci\xF3n",
      "Devolucion",
      "Reembolsado",
      "Reembolsada",
      "Reembolso",
      "Reintegrado",
      "Reintegrada"
    ]
  },
  {
    locale: "it",
    keywords: [
      "Consegnato",
      "Consegnata",
      "Ritirato",
      "Ritirata",
      "Probabile consegna",
      "Consegna prevista",
      "In arrivo",
      "Spedito",
      "Spedita",
      "Annullato",
      "Annullata",
      "Reso completato",
      "Reso avviato",
      "Restituito",
      "Restituita",
      "Rimborsato",
      "Rimborsata",
      "Rimborso"
    ]
  }
];
var japaneseStatusKeywords = [
  "\u914D\u9054\u3057\u307E\u3057\u305F",
  "\u914D\u9054\u6E08\u307F",
  "\u914D\u9054\u5B8C\u4E86",
  "\u304A\u5C4A\u3051\u6E08\u307F",
  "\u767A\u9001\u3057\u307E\u3057\u305F",
  "\u767A\u9001\u6E08\u307F",
  "\u304A\u5C4A\u3051\u4E88\u5B9A",
  "\u5230\u7740\u4E88\u5B9A",
  "\u914D\u9054\u4E88\u5B9A",
  "\u30AD\u30E3\u30F3\u30BB\u30EB\u3055\u308C\u307E\u3057\u305F",
  "\u30AD\u30E3\u30F3\u30BB\u30EB\u6E08\u307F",
  "\u8FD4\u54C1\u304C\u5B8C\u4E86\u3057\u307E\u3057\u305F",
  "\u8FD4\u54C1\u5B8C\u4E86",
  "\u8FD4\u54C1\u6E08\u307F",
  "\u8FD4\u91D1\u3057\u307E\u3057\u305F",
  "\u8FD4\u91D1\u6E08\u307F"
];
var JAPANESE_STATUS_MAX_LENGTH = 40;
var japaneseStatusPattern = new RegExp(
  `^[0-9\uFF10-\uFF19/:\uFF1A()\uFF08\uFF09\\s\\p{Script=Han}]{0,16}?\u306B?(?:${japaneseStatusKeywords.join("|")})`,
  "u"
);
var blockedStatusCandidates = [/^Shipped\s+and\s+sold\b/iu];
function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
var statusPatterns = localeStatusConfigs.map((config) => {
  const keywords = config.keywords.map((keyword) => escapeRegex(keyword)).join("|");
  return new RegExp(`^((?:${keywords})(?:\\s+${STATUS_TOKEN}+){0,7})`, "iu");
});
function getStatusCandidates(orderText) {
  const normalized = orderText.replace(/\u00a0/g, " ").trim();
  if (!normalized) return [];
  const byLine = normalized.split(/\r?\n+/).map((line) => line.replace(/\s+/g, " ").trim()).filter(Boolean);
  if (byLine.length > 1) return byLine;
  const byChunk = normalized.split(/\s{2,}|\s[|]\s|\s[-–—]\s/).map((chunk) => chunk.replace(/\s+/g, " ").trim()).filter(Boolean);
  return byChunk.length > 0 ? byChunk : [normalized.replace(/\s+/g, " ").trim()];
}
function parseOrderStatus(orderText) {
  if (!orderText) return "";
  const candidates = getStatusCandidates(orderText);
  for (const candidate of candidates) {
    if (blockedStatusCandidates.some((pattern) => pattern.test(candidate))) {
      continue;
    }
    for (const pattern of statusPatterns) {
      const match = candidate.match(pattern);
      if (match?.[1]) {
        return match[1].trim().substring(0, 50);
      }
    }
    if (candidate.length <= JAPANESE_STATUS_MAX_LENGTH && japaneseStatusPattern.test(candidate)) {
      return candidate;
    }
  }
  return "";
}

// vendor/src/utils/transactionUtils.ts
function buildTransactionUrl(origin, orderId) {
  return `${origin}/cpe/yourpayments/transactions?transactionTag=${encodeURIComponent(orderId)}`;
}
function formatTransactionDatesForCSV(transactions) {
  if (transactions.length === 0) return "";
  return transactions.map((t) => t.date).join(" | ");
}
function formatTransactionAmountsForCSV(transactions) {
  if (transactions.length === 0) return "";
  return transactions.map((t) => String(t.amount)).join(" | ");
}
function parseCPETransactionAmount(amountText, hostname) {
  const isDebit = /^[-−]/.test(amountText.trim());
  const price = extractPriceFromText(amountText, hostname);
  if (!price || price.amount === 0) return null;
  return {
    amount: isDebit ? price.amount : -price.amount,
    currency: price.currency
  };
}
function buildTransactionsFromCPEEntries(entries, hostname) {
  const transactions = [];
  for (const { date, amountText } of entries) {
    const parsed = parseCPETransactionAmount(amountText, hostname);
    if (!parsed) continue;
    transactions.push({ date, amount: parsed.amount, currency: parsed.currency });
  }
  return transactions;
}

// vendor/src/utils/csvUtils.ts
function escapeCSVValue(value) {
  if (value === void 0 || value === null) return "";
  const str = String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}
function formatPromotionsForCSV(promotions, currency = "EUR") {
  const currencyPrefix = currency === "EUR" ? "\u20AC" : `${currency} `;
  return promotions.map((p) => `${p.description}: ${currencyPrefix}${p.amount}`).join("; ");
}
function convertOrdersToCSV(orders, getHeader = (key) => key, includeTransactions = false) {
  const headers = [
    getHeader("csvHeaderOrderId"),
    getHeader("csvHeaderOrderDate"),
    getHeader("csvHeaderTotalAmount"),
    getHeader("csvHeaderCurrency"),
    getHeader("csvHeaderTotalSavings"),
    getHeader("csvHeaderStatus"),
    getHeader("csvHeaderItemTitle"),
    getHeader("csvHeaderItemAsin"),
    getHeader("csvHeaderItemQuantity"),
    getHeader("csvHeaderItemPrice"),
    getHeader("csvHeaderItemDiscount"),
    getHeader("csvHeaderPromotions"),
    getHeader("csvHeaderItemUrl"),
    getHeader("csvHeaderDetailsUrl"),
    getHeader("csvHeaderRecipientName"),
    getHeader("csvHeaderRecipientStreet"),
    getHeader("csvHeaderRecipientCityPostal"),
    getHeader("csvHeaderRecipientCountry"),
    getHeader("csvHeaderChargedAmount"),
    getHeader("csvHeaderGiftCardAmount")
  ];
  if (includeTransactions) {
    headers.push(getHeader("csvHeaderTransactionDates"));
    headers.push(getHeader("csvHeaderTransactionAmounts"));
  }
  const rows = [headers.join(",")];
  orders.forEach((order) => {
    const promotionsStr = formatPromotionsForCSV(order.promotions, order.currency);
    const transactions = order.transactions ?? [];
    const txDates = includeTransactions ? escapeCSVValue(formatTransactionDatesForCSV(transactions)) : null;
    const txAmounts = includeTransactions ? escapeCSVValue(formatTransactionAmountsForCSV(transactions)) : null;
    const txColumns = (firstRow) => {
      if (!includeTransactions) return [];
      return firstRow ? [txDates ?? "", txAmounts ?? ""] : ["", ""];
    };
    if (order.items.length === 0) {
      rows.push(
        [
          escapeCSVValue(order.orderId),
          escapeCSVValue(order.orderDate),
          order.totalAmount,
          escapeCSVValue(order.currency),
          order.totalSavings,
          escapeCSVValue(order.orderStatus),
          "",
          "",
          "",
          "",
          "",
          escapeCSVValue(promotionsStr),
          "",
          escapeCSVValue(order.detailsUrl),
          escapeCSVValue(order.recipientName),
          escapeCSVValue(order.recipientStreet),
          escapeCSVValue(order.recipientCityPostal),
          escapeCSVValue(order.recipientCountry),
          order.chargedAmount ?? "",
          order.giftCardAmount,
          ...txColumns(true)
        ].join(",")
      );
    } else {
      order.items.forEach((item, index) => {
        rows.push(
          [
            escapeCSVValue(order.orderId),
            escapeCSVValue(order.orderDate),
            order.totalAmount,
            escapeCSVValue(order.currency),
            index === 0 ? order.totalSavings : "",
            escapeCSVValue(order.orderStatus),
            escapeCSVValue(item.title),
            escapeCSVValue(item.asin),
            item.quantity,
            item.price,
            item.discount,
            index === 0 ? escapeCSVValue(promotionsStr) : "",
            escapeCSVValue(item.itemUrl),
            escapeCSVValue(order.detailsUrl),
            index === 0 ? escapeCSVValue(order.recipientName) : "",
            index === 0 ? escapeCSVValue(order.recipientStreet) : "",
            index === 0 ? escapeCSVValue(order.recipientCityPostal) : "",
            index === 0 ? escapeCSVValue(order.recipientCountry) : "",
            index === 0 ? order.chargedAmount ?? "" : "",
            index === 0 ? order.giftCardAmount : "",
            ...txColumns(index === 0)
          ].join(",")
        );
      });
    }
  });
  return rows.join("\n");
}

// vendor/src/utils/urlUtils.ts
var AMAZON_LOCALE_PREFIX = /^\/-\/[a-z]{2}(?:[-_][a-z]{2})?(?=\/)/i;
function buildOrderPageUrl(baseUrl, year, startIndex = 0) {
  try {
    const urlObj = new URL(baseUrl);
    urlObj.searchParams.set("timeFilter", `year-${year}`);
    if (startIndex > 0) {
      urlObj.searchParams.set("startIndex", startIndex.toString());
    } else {
      urlObj.searchParams.delete("startIndex");
    }
    return urlObj.toString();
  } catch {
    const params = new URLSearchParams();
    params.set("timeFilter", `year-${year}`);
    if (startIndex > 0) {
      params.set("startIndex", startIndex.toString());
    }
    return `${baseUrl}?${params.toString()}`;
  }
}
var ORDER_PATHS = [
  "/gp/your-account/order-history",
  "/gp/css/order-history",
  "/your-orders/orders",
  "/your-orders"
];
function getAmazonLocalePrefix(pathname) {
  return pathname.match(AMAZON_LOCALE_PREFIX)?.[0] || "";
}
function normalizeAmazonPath(pathname) {
  const localePrefix = getAmazonLocalePrefix(pathname);
  return localePrefix ? pathname.slice(localePrefix.length) || "/" : pathname;
}
function getMatchedOrderPath(pathname) {
  const normalizedPath = normalizeAmazonPath(pathname);
  const matchedPath = [...ORDER_PATHS].sort((a, b) => b.length - a.length).find((path) => normalizedPath.startsWith(path));
  return matchedPath || null;
}
function getOrderHistoryBaseUrl(url) {
  try {
    const urlObj = new URL(url);
    const localePrefix = getAmazonLocalePrefix(urlObj.pathname);
    const matchedPath = getMatchedOrderPath(urlObj.pathname);
    if (matchedPath) {
      const preferredPath = matchedPath === "/your-orders" ? "/your-orders/orders" : matchedPath;
      return `${urlObj.origin}${localePrefix}${preferredPath}`;
    }
    return `${urlObj.origin}${localePrefix}/your-orders/orders`;
  } catch {
    return "";
  }
}
function extractAsinFromUrl(url) {
  const asinMatch = url.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:\/|$|\?)?/i);
  return asinMatch?.[1]?.toUpperCase() || null;
}

// vendor/src/utils/invoiceUtils.ts
function buildInvoicePopoverUrl(origin, orderId) {
  return `${origin}/your-orders/invoice/popover?orderId=${encodeURIComponent(
    orderId
  )}&ref_=fed_invoice_ajax`;
}
function isPdfInvoiceHref(href) {
  if (!href) return false;
  const normalized = href.trim().toLowerCase();
  if (normalized.startsWith("javascript:")) return false;
  if (normalized.includes("/gp/help/")) return false;
  if (normalized.includes("/summary/print.html")) return false;
  if (normalized.includes("/summary/print.htm")) return false;
  return /\.pdf(?:$|[?#])/i.test(normalized) || normalized.includes("/documents/download/");
}
function buildInvoiceFilename(orderId, index, total, subfolder) {
  const suffix = total > 1 ? `_${index + 1}` : "";
  const base = `${orderId}${suffix}.pdf`;
  return subfolder ? `${subfolder}/${base}` : base;
}
async function downloadInvoicesForOrder(orderId, origin, subfolder, deps) {
  if (deps.isStopRequested()) return 0;
  const hrefs = await deps.fetchPdfHrefs(buildInvoicePopoverUrl(origin, orderId));
  if (hrefs === null || deps.isStopRequested()) return 0;
  if (hrefs.length === 0) {
    deps.warn(`[Amazon Exporter] No PDF invoice link found in popover for ${orderId}`);
    return 0;
  }
  let started = 0;
  for (let i = 0; i < hrefs.length; i++) {
    if (deps.isStopRequested()) break;
    const href = hrefs[i];
    if (!href) continue;
    const data = {
      url: new URL(href, origin).toString(),
      fileName: buildInvoiceFilename(orderId, i, hrefs.length, subfolder)
    };
    try {
      const response = await deps.download(data);
      if (response?.success) {
        started++;
      } else {
        deps.warn(
          `[Amazon Exporter] Invoice download failed for ${orderId}:`,
          response?.error ?? "no response from background"
        );
      }
    } catch (error) {
      deps.warn(`[Amazon Exporter] Failed to dispatch invoice download for ${orderId}:`, error);
    }
  }
  return started;
}

// vendor/src/constants.ts
var STORAGE_KEY = "fireflySidecarAmazonSync.v1";
var STOP_FLAG_KEY = "fireflySidecarAmazonSyncStopRequested";
var INVOICE_DOWNLOAD_SUBFOLDER = "amazon-invoices";

// vendor/src/content/content.ts
(function() {
  "use strict";
  let stopRequested = false;
  function getMessage(key, substitutions) {
    return import_webextension_polyfill.default.i18n.getMessage(key, substitutions) || key;
  }
  checkExportState();
  import_webextension_polyfill.default.runtime.onMessage.addListener((message, _sender) => {
    const msg = message;
    if (msg.action === "exportOrders" && msg.options) {
      startExport(msg.options);
      return Promise.resolve({ success: true, message: "Export started" });
    }
    if (msg.action === "getExportStatus") {
      const state = getExportState();
      return Promise.resolve(state ? { success: true, ...state } : { success: false });
    }
    if (msg.action === "stopExport") {
      stopRequested = true;
      clearExportState();
      import_webextension_polyfill.default.runtime.sendMessage({ action: "exportStopped" }).catch(() => {
        console.debug("[Amazon Exporter] Popup not reachable for exportStopped notification");
      });
      return Promise.resolve({ success: true });
    }
    return void 0;
  });
  import_webextension_polyfill.default.runtime.sendMessage({ action: "collectorReady", page: "orders" }).catch(() => {
  });
  function getExportState() {
    try {
      const data = sessionStorage.getItem(STORAGE_KEY);
      if (!data) return null;
      const state = JSON.parse(data);
      if (typeof state.includeTransactions !== "boolean") {
        state.includeTransactions = false;
      }
      if (typeof state.downloadInvoices !== "boolean") {
        state.downloadInvoices = false;
      }
      return state;
    } catch {
      return null;
    }
  }
  function saveExportState(state) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }
  function clearExportState() {
    sessionStorage.removeItem(STORAGE_KEY);
  }
  function checkExportState() {
    const run = () => {
      setTimeout(async () => {
        try {
          const stopFlag = await import_webextension_polyfill.default.storage.session.get(STOP_FLAG_KEY);
          if (stopFlag[STOP_FLAG_KEY]) {
            await import_webextension_polyfill.default.storage.session.remove(STOP_FLAG_KEY);
            clearExportState();
            return;
          }
        } catch {
          console.debug("[Amazon Exporter] Could not read stop flag from storage.session");
        }
        const state = getExportState();
        if (state && state.inProgress) {
          console.log("[Amazon Exporter]", getMessage("resumingExport"), state);
          continueExport(state);
        }
      }, 1500);
    };
    if (document.readyState === "complete") {
      run();
    } else {
      window.addEventListener("load", run, { once: true });
    }
  }
  function startExport(options) {
    stopRequested = false;
    const { format, startDate, endDate, exportAll, includeTransactions, downloadInvoices } = options;
    const years = getAvailableYears();
    console.log("[Amazon Exporter] Found years:", years);
    const yearsToProcess = exportAll ? [...years] : filterYearsByDateRange(years, startDate, endDate);
    console.log("[Amazon Exporter] Years to process:", yearsToProcess);
    if (yearsToProcess.length === 0) {
      alert(getMessage("noYearsFound"));
      return;
    }
    const state = {
      inProgress: true,
      format,
      startDate,
      endDate,
      exportAll,
      includeTransactions,
      downloadInvoices,
      yearsToProcess,
      currentYearIndex: 0,
      currentStartIndex: 0,
      collectedOrders: [],
      seenOrderIds: [],
      baseUrl: getOrderHistoryBaseUrl(window.location.href)
    };
    saveExportState(state);
    const firstYear = yearsToProcess[0];
    if (!firstYear) return;
    const firstUrl = buildOrderPageUrl(state.baseUrl, firstYear, 0);
    console.log("[Amazon Exporter] Starting export, navigating to:", firstUrl);
    if (window.location.href.includes(`timeFilter=year-${firstYear}`) && !window.location.href.includes("startIndex")) {
      scrapeCurrentPageAndContinue(state);
    } else {
      window.location.href = firstUrl;
    }
  }
  function continueExport(state) {
    if (stopRequested || !getExportState()) {
      return;
    }
    const currentYear = state.yearsToProcess[state.currentYearIndex];
    const pageNum = String(Math.floor(state.currentStartIndex / 10) + 1);
    updateProgress(
      calculateProgress(state),
      getMessage("processingYear", [currentYear || "", pageNum])
    );
    scrapeCurrentPageAndContinue(state);
  }
  function scrapeCurrentPageAndContinue(state) {
    if (stopRequested || !getExportState()) {
      return;
    }
    const startDateObj = state.startDate ? new Date(state.startDate) : null;
    const endDateObj = state.endDate ? new Date(state.endDate) : null;
    const { orders: pageOrders, passedStartDate } = scrapeVisibleOrders(
      startDateObj,
      endDateObj,
      state.exportAll,
      new Set(state.seenOrderIds)
    );
    console.log("[Amazon Exporter] Found", pageOrders.length, "orders on this page");
    pageOrders.forEach((order) => {
      if (!state.seenOrderIds.includes(order.orderId)) {
        state.collectedOrders.push(order);
        state.seenOrderIds.push(order.orderId);
      }
    });
    const hasNextPage = checkForNextPage();
    if (hasNextPage && !passedStartDate) {
      state.currentStartIndex += 10;
      saveExportState(state);
      const currentYear = state.yearsToProcess[state.currentYearIndex];
      if (!currentYear) return;
      const nextUrl = buildOrderPageUrl(state.baseUrl, currentYear, state.currentStartIndex);
      console.log("[Amazon Exporter] Navigating to next page:", nextUrl);
      window.location.href = nextUrl;
      return;
    }
    state.currentYearIndex++;
    state.currentStartIndex = 0;
    if (state.currentYearIndex < state.yearsToProcess.length) {
      saveExportState(state);
      const nextYear = state.yearsToProcess[state.currentYearIndex];
      if (!nextYear) return;
      const nextUrl = buildOrderPageUrl(state.baseUrl, nextYear, 0);
      console.log("[Amazon Exporter] Navigating to next year:", nextUrl);
      window.location.href = nextUrl;
      return;
    }
    finishExport(state);
  }
  async function finishExport(state) {
    console.log("[Amazon Exporter] Export complete. Total orders:", state.collectedOrders.length);
    updateProgress(
      80,
      state.includeTransactions ? getMessage("fetchingPricesAndTransactions", [String(state.collectedOrders.length)]) : getMessage("fetchingPrices", [String(state.collectedOrders.length)])
    );
    if (state.downloadInvoices) {
      await setDownloadsUIEnabled(false);
    }
    try {
      await fetchOrderDetailsForPrices(
        state.collectedOrders,
        state.includeTransactions,
        state.downloadInvoices
      );
    } finally {
      if (state.downloadInvoices) {
        await setDownloadsUIEnabled(true);
      }
    }
    if (stopRequested || !getExportState()) {
      return;
    }
    const orders = state.collectedOrders.map((order) => ({
      orderId: order.orderId,
      orderDate: order.orderDate,
      totalAmount: order.totalAmount,
      currency: order.currency,
      items: order.items,
      chargedAmount: order.chargedAmount,
      giftCardAmount: order.giftCardAmount,
      transactions: order.transactions,
      orderStatus: order.orderStatus
    }));
    const response = await import_webextension_polyfill.default.runtime.sendMessage({ action: "sidecarOrders", orders });
    if (!response.success) {
      updateProgress(100, response.error || "Sync failed. Open extension and retry sending.");
      return;
    }
    clearExportState();
  }
  function calculateProgress(state) {
    const yearProgress = state.currentYearIndex / state.yearsToProcess.length;
    const pageProgress = Math.min(state.currentStartIndex / 100, 0.9);
    return Math.floor((yearProgress + pageProgress / state.yearsToProcess.length) * 75) + 5;
  }
  function getAvailableYears() {
    const years = [];
    const selectors = [
      "#time-filter",
      "#orderFilter",
      'select[name="timeFilter"]',
      'select[name="orderFilter"]',
      '[data-action="a-dropdown-button"]',
      ".a-dropdown-container select",
      "#a-autoid-1-announce",
      '[id*="dropdown"] select',
      "form select"
    ];
    for (const selector of selectors) {
      const dropdown = document.querySelector(selector);
      if (dropdown) {
        const options = dropdown.querySelectorAll("option");
        options.forEach((option) => {
          const value = option.value || option.textContent || "";
          const year = extractOrderYear(value);
          if (year) {
            years.push(year);
          }
        });
        if (years.length > 0) break;
      }
    }
    const yearLinks = document.querySelectorAll('a[href*="timeFilter=year-"]');
    yearLinks.forEach((link) => {
      const href = link.href;
      const year = extractOrderYear(href);
      if (year && !years.includes(year)) {
        years.push(year);
      }
    });
    const dropdownItems = document.querySelectorAll(
      '[data-value*="year-"], .a-popover-inner li, #orderFilter option'
    );
    dropdownItems.forEach((item) => {
      const value = item.getAttribute("data-value") || item.value || item.textContent || "";
      const year = extractOrderYear(value);
      if (year && !years.includes(year)) {
        years.push(year);
      }
    });
    if (years.length === 0) {
      const currentYear = (/* @__PURE__ */ new Date()).getFullYear();
      for (let y = currentYear; y >= currentYear - 10; y--) {
        years.push(y.toString());
      }
    }
    return [...new Set(years)].sort((a, b) => Number(b) - Number(a));
  }
  function checkForNextPage() {
    const nextSelectors = [
      ".a-pagination .a-last:not(.a-disabled) a",
      'a[aria-label*="N\xE4chste"]',
      'a[aria-label*="N\xE4sta"]',
      'a[aria-label*="Next"]',
      'a[aria-label*="Siguiente"]',
      'a[aria-label*="\u6B21"]',
      ".a-pagination li:last-child:not(.a-disabled) a",
      "a.a-last:not(.a-disabled)"
    ];
    for (const selector of nextSelectors) {
      const nextBtn = document.querySelector(selector);
      if (nextBtn) {
        console.log("[Amazon Exporter] Next page button found");
        return true;
      }
    }
    return false;
  }
  function scrapeVisibleOrders(startDateObj, endDateObj, exportAll, seenOrderIds) {
    const orders = [];
    let passedStartDate = false;
    console.log("[Amazon Exporter] Scraping visible page...");
    console.log("[Amazon Exporter] URL:", window.location.href);
    const orderSelectors = [
      ".order-card",
      ".order",
      '[data-component="orderCard"]',
      ".a-box-group.order",
      ".your-orders-content-container .a-box-group",
      "#ordersContainer .order-card",
      ".js-order-card",
      '[class*="order-card"]'
    ];
    let orderElements = document.querySelectorAll(".__nonexistent__");
    for (const selector of orderSelectors) {
      orderElements = document.querySelectorAll(selector);
      if (orderElements.length > 0) {
        console.log(
          `[Amazon Exporter] Found ${orderElements.length} orders with selector: ${selector}`
        );
        break;
      }
    }
    if (orderElements.length === 0) {
      const orderIdPattern = new RegExp(ORDER_ID_PATTERN);
      const potentialOrders = /* @__PURE__ */ new Set();
      document.querySelectorAll("*").forEach((el) => {
        if (el.textContent && orderIdPattern.test(el.textContent)) {
          let parent = el;
          for (let i = 0; i < 10 && parent?.parentElement; i++) {
            parent = parent.parentElement;
            if (parent.classList.contains("a-box") || parent.classList.contains("a-box-group") || parent.tagName === "DIV" && parent.children.length > 3) {
              potentialOrders.add(parent);
              break;
            }
          }
        }
      });
      orderElements = Array.from(potentialOrders);
      console.log(`[Amazon Exporter] Fallback found ${orderElements.length} order containers`);
    }
    orderElements.forEach((orderEl, index) => {
      try {
        const order = parseOrderElement(orderEl);
        if (order && order.orderId) {
          if (seenOrderIds.has(order.orderId)) {
            return;
          }
          if (!exportAll && startDateObj && endDateObj && order.orderDate) {
            const orderDateObj = new Date(order.orderDate);
            if (orderDateObj < startDateObj) {
              passedStartDate = true;
              console.log(
                `[Amazon Exporter] Skipping order ${order.orderId}: date ${order.orderDate} before range start ${startDateObj.toISOString().split("T")[0]}`
              );
              return;
            }
            if (orderDateObj > endDateObj) {
              console.log(
                `[Amazon Exporter] Skipping order ${order.orderId}: date ${order.orderDate} after range end ${endDateObj.toISOString().split("T")[0]}`
              );
              return;
            }
          }
          orders.push(order);
          console.log(
            `[Amazon Exporter] Parsed order: ${order.orderId}, ${order.orderDate}, ${order.totalAmount} ${order.currency}`
          );
        }
      } catch (error) {
        console.warn(`[Amazon Exporter] Failed to parse order ${index}:`, error);
      }
    });
    return { orders, passedStartDate };
  }
  function getOrderCardText(orderEl) {
    const clone = orderEl.cloneNode(true);
    clone.querySelectorAll("script, style, noscript").forEach((el) => el.remove());
    return clone.textContent || "";
  }
  function getOrderHeaderRows(orderEl) {
    const rows = [];
    const items = orderEl.querySelectorAll(".order-header__header-list-item");
    items.forEach((item) => {
      const rowEls = item.querySelectorAll(":scope > .a-row");
      if (rowEls.length >= 2) {
        rows.push({
          label: (rowEls[0]?.textContent || "").replace(/\s+/g, " ").trim(),
          value: (rowEls[1]?.textContent || "").replace(/\s+/g, " ").trim()
        });
      }
    });
    return rows;
  }
  function parseOrderElement(orderEl) {
    const order = {
      orderId: "",
      orderDate: "",
      totalAmount: 0,
      currency: getCurrencyForDomain(window.location.hostname) ?? "EUR",
      items: [],
      orderStatus: "",
      detailsUrl: "",
      promotions: [],
      totalSavings: 0,
      recipientName: "",
      recipientStreet: "",
      recipientCityPostal: "",
      recipientCountry: "",
      chargedAmount: null,
      giftCardAmount: 0
    };
    const orderText = getOrderCardText(orderEl);
    order.orderId = extractOrderId(orderText) || "";
    if (!order.orderId) {
      const links = orderEl.querySelectorAll("a[href]");
      for (const link of links) {
        const href = link.getAttribute("href") || "";
        const orderId = extractOrderIdFromUrl(href);
        if (orderId) {
          order.orderId = orderId;
          break;
        }
      }
    }
    if (!order.orderId) {
      const attrTargets = [
        orderEl,
        ...Array.from(orderEl.querySelectorAll("[data-order-id], [data-orderid], [data-order]"))
      ];
      for (const el of attrTargets) {
        if (!el) continue;
        const raw = el.getAttribute("data-order-id") || el.getAttribute("data-orderid") || el.getAttribute("data-order") || el.id || "";
        const match = raw.match(/\d{3}-\d{7}-\d{7}/);
        if (match?.[0]) {
          order.orderId = match[0];
          break;
        }
      }
    }
    if (!order.orderId) {
      const allLinks = orderEl.querySelectorAll("a[href]");
      for (const link of allLinks) {
        const href = link.href || link.getAttribute("href") || "";
        const match = href.match(/\d{3}-\d{7}-\d{7}/);
        if (match?.[0]) {
          order.orderId = match[0];
          break;
        }
      }
    }
    if (!order.orderId) {
      const snippet = orderText.replace(/\s+/g, " ").trim().substring(0, 150);
      console.warn(`[Amazon Exporter] Could not extract order ID. Card text: "${snippet}"`);
    }
    const detailsLink = orderEl.querySelector(
      'a[href*="order-details"], a[href*="orderID="], a[href*="orderId="]'
    );
    if (detailsLink) {
      order.detailsUrl = detailsLink.href;
      if (!order.orderId) {
        order.orderId = extractOrderIdFromUrl(order.detailsUrl) || "";
      }
    }
    const headerRows = getOrderHeaderRows(orderEl);
    order.orderDate = parseOrderDateFromRows(headerRows) || parseOrderDate(orderText);
    const priceResult = extractTotalFromRows(headerRows, window.location.hostname) || extractPriceFromText(orderText, window.location.hostname);
    if (priceResult) {
      order.totalAmount = priceResult.amount;
      order.currency = priceResult.currency;
    }
    order.orderStatus = parseOrderStatus(orderText);
    order.items = parseOrderItems(orderEl);
    const recipient = parseRecipient(orderEl);
    order.recipientName = recipient.name;
    order.recipientStreet = recipient.street;
    order.recipientCityPostal = recipient.cityPostal;
    order.recipientCountry = recipient.country;
    if (isAdvertisementOrder(order)) {
      console.log("[Amazon Exporter] Skipping advertisement order:", order.orderId);
      return null;
    }
    return order;
  }
  function parseRecipient(orderEl) {
    const result = { name: "", street: "", cityPostal: "", country: "" };
    const recipientEl = orderEl.querySelector(".yohtmlc-recipient");
    if (!recipientEl) return result;
    const triggerEl = recipientEl.querySelector(
      "a.a-popover-trigger, .insert-encrypted-trigger-text"
    );
    if (triggerEl) {
      result.name = (triggerEl.textContent || "").trim();
    }
    const preloadEl = recipientEl.querySelector(".a-popover-preload");
    if (!preloadEl) return result;
    const rows = preloadEl.querySelectorAll(".a-row");
    if (rows.length === 0) return result;
    if (!result.name) {
      const h5 = preloadEl.querySelector("h5");
      if (h5) result.name = (h5.textContent || "").trim();
    }
    const addressRows = [];
    rows.forEach((row) => {
      if (!row.querySelector("h5")) addressRows.push(row);
    });
    if (addressRows.length === 0) return result;
    const countryEl = addressRows[addressRows.length - 1];
    if (countryEl) {
      result.country = (countryEl.textContent || "").trim();
    }
    const streetRows = addressRows.slice(0, -1);
    const allLines = [];
    streetRows.forEach((row) => {
      const html = row.innerHTML.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "");
      const decoded = decodeHtmlEntities(html);
      decoded.split("\n").map((line) => line.trim()).filter(Boolean).forEach((line) => allLines.push(line));
    });
    if (allLines.length === 0) return result;
    result.cityPostal = allLines[allLines.length - 1] ?? "";
    result.street = allLines.slice(0, -1).join(", ");
    return result;
  }
  let entityDecoderTextarea = null;
  function decodeHtmlEntities(text) {
    if (!entityDecoderTextarea) {
      entityDecoderTextarea = document.createElement("textarea");
    }
    entityDecoderTextarea.innerHTML = text;
    return entityDecoderTextarea.value;
  }
  function parseOrderItems(orderEl) {
    const items = [];
    const seenAsins = /* @__PURE__ */ new Set();
    const productLinks = orderEl.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]');
    productLinks.forEach((link) => {
      const href = link.getAttribute("href") || link.href || "";
      const asin = extractAsinFromUrl(href);
      if (!asin) return;
      if (seenAsins.has(asin)) return;
      seenAsins.add(asin);
      const item = {
        title: "",
        asin,
        quantity: 1,
        price: 0,
        discount: 0,
        // Derive from the marketplace being scraped - hardcoding amazon.de
        // produced wrong links for every other marketplace
        itemUrl: `${window.location.origin}/dp/${asin}`
      };
      let title = link.textContent?.trim() || "";
      if (!title || title.length < 5) {
        let parent = link.parentElement;
        for (let i = 0; i < 5 && parent; i++) {
          const titleEl = parent.querySelector(
            '.a-text-bold, [class*="product-title"], [class*="item-title"]'
          );
          if (titleEl && titleEl.textContent?.trim().length && titleEl.textContent.trim().length > 5) {
            title = titleEl.textContent.trim();
            break;
          }
          parent = parent.parentElement;
        }
      }
      if (!title || title.length < 5) {
        title = link.title || link.getAttribute("aria-label") || "";
      }
      if (!title || title.length < 5) {
        const img = link.querySelector("img") || link.parentElement?.querySelector("img");
        if (img?.alt) title = img.alt;
      }
      item.title = title.replace(/\s+/g, " ").trim();
      let foundQuantity = false;
      const itemRow = link.closest('[data-component="purchasedItems"], .a-fixed-left-grid') || link.parentElement;
      if (itemRow) {
        const qtyBadge = itemRow.querySelector(
          '.od-item-view-qty span, .product-image__qty, [class*="qty-badge"], [class*="quantity-badge"]'
        );
        if (qtyBadge?.textContent) {
          const qty = parseInt(qtyBadge.textContent.trim(), 10);
          if (!isNaN(qty) && qty > 0) {
            item.quantity = qty;
            foundQuantity = true;
          }
        }
      }
      if (!foundQuantity && itemRow) {
        const nonTitleText = itemRow.textContent?.replace(item.title, "") || "";
        const qtyMatch = nonTitleText.match(
          /(?:Qty|Quantity|Menge|Anzahl|Antal|Cantidad|Cant\.?|数量)[:：\s]*(\d+)/i
        );
        if (qtyMatch?.[1]) {
          const parsedQty = parseInt(qtyMatch[1], 10);
          if (!isNaN(parsedQty) && parsedQty > 0) {
            item.quantity = parsedQty;
          }
        }
      }
      if (item.title || item.asin) {
        items.push(item);
      }
    });
    return items;
  }
  async function fetchOrderDetailsForPrices(orders, includeTransactions, downloadInvoices) {
    const ordersNeedingDetails = orders.filter((order) => order.detailsUrl);
    console.log("[Amazon Exporter] Fetching details for", ordersNeedingDetails.length, "orders");
    for (let i = 0; i < ordersNeedingDetails.length; i++) {
      if (stopRequested || !getExportState()) {
        break;
      }
      const order = ordersNeedingDetails[i];
      if (!order) continue;
      try {
        updateProgress(
          80 + i / ordersNeedingDetails.length * 10,
          getMessage("fetchingPricesProgress", [String(i + 1), String(ordersNeedingDetails.length)])
        );
        const response = await fetch(order.detailsUrl, {
          credentials: "include"
        });
        if (response.ok) {
          const html = await response.text();
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, "text/html");
          parseItemPricesFromDetails(order, doc);
          parsePromotionsFromDetails(order, doc);
          parsePaymentSummaryFromDetails(order, doc);
        }
        if (includeTransactions && order.orderId) {
          let transactionOrigin = "";
          let transactionHost = "";
          try {
            const detailsUrl = new URL(order.detailsUrl);
            transactionOrigin = detailsUrl.origin;
            transactionHost = detailsUrl.hostname;
          } catch {
            console.warn(
              "[Amazon Exporter] Could not derive origin from detailsUrl for order:",
              order.orderId
            );
          }
          if (transactionOrigin) {
            await new Promise((resolve) => setTimeout(resolve, 200));
            const txUrl = buildTransactionUrl(transactionOrigin, order.orderId);
            try {
              const txResponse = await fetch(txUrl, { credentials: 'include' });
              if (!txResponse.ok) {
                console.warn(`[Amazon Exporter] Payment-page request failed (HTTP ${txResponse.status}) for ${order.orderId}; existing payment data is kept.`);
              } else {
                const txHtml = await txResponse.text();
                const txParser = new DOMParser();
                const txDoc = txParser.parseFromString(txHtml, 'text/html');
                const needsLogin = /\/ap\/(signin|cvf)|validateCaptcha/i.test(txResponse.url || '') ||
                  Boolean(txDoc.querySelector('#ap_email, #ap_password, #captchacharacters, form[name="signIn"]'));
                if (needsLogin) {
                  console.warn(`[Amazon Exporter] Amazon sign-in or verification blocked payment details for ${order.orderId}; existing payment data is kept.`);
                } else {
                  const transactions = parseTransactionsFromCPEDoc(txDoc, transactionHost);
                  if (transactions.length > 0) {
                    order.transactions = transactions;
                    console.log(`[Amazon Exporter] ${transactions.length} transaction(s) from payment page for order ${order.orderId}`);
                  } else {
                    console.info(`[Amazon Exporter] No supplemental payment rows could be read for ${order.orderId}. The order is still collected; existing payment data and order-summary amounts are kept. Payment dates may be unavailable.`);
                  }
                }
              }
            } catch (txError) {
              console.warn(
                "[Amazon Exporter] Error fetching transactions for order:",
                order.orderId,
                txError
              );
            }
          }
        }
        if (downloadInvoices && order.orderId) {
          let orderOrigin = "";
          try {
            orderOrigin = new URL(order.detailsUrl).origin;
          } catch {
            console.warn(
              "[Amazon Exporter] Could not derive origin from detailsUrl for order:",
              order.orderId
            );
          }
          if (orderOrigin) {
            await new Promise((resolve) => setTimeout(resolve, 200));
            try {
              await downloadInvoicePdfsForOrder(order.orderId, orderOrigin);
            } catch (invoiceError) {
              console.warn(
                "[Amazon Exporter] Error downloading invoices for order:",
                order.orderId,
                invoiceError
              );
            }
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 200));
      } catch (error) {
        console.warn("[Amazon Exporter] Error fetching details:", error);
      }
    }
  }
  function parseTransactionsFromCPEDoc(doc, hostname) {
    const entries = [];
    const seen = /* @__PURE__ */ new Set();
    const groups = doc.querySelectorAll(".a-box-group");
    for (const group of groups) {
      const dateEl = group.querySelector(".apx-transaction-date-container span");
      if (!dateEl) continue;
      const dateText = dateEl.textContent?.trim() ?? "";
      const date = parseOrderDate(dateText);
      if (!date) continue;
      const amountEls = group.querySelectorAll(
        ".a-column.a-span3.a-text-right.a-span-last .a-size-base-plus.a-text-bold,.apx-transactions-line-item-component-container .a-size-base-plus.a-text-bold"
      );
      for (const amountEl of amountEls) {
        const amountText = amountEl.textContent?.trim() ?? "";
        if (!amountText) continue;
        if (seen.has(amountEl)) continue;
        seen.add(amountEl);
        entries.push({ date, amountText });
      }
    }
    return buildTransactionsFromCPEEntries(entries, hostname);
  }
  async function downloadInvoicePdfsForOrder(orderId, origin) {
    await downloadInvoicesForOrder(orderId, origin, INVOICE_DOWNLOAD_SUBFOLDER, {
      async fetchPdfHrefs(popoverUrl) {
        const response = await fetch(popoverUrl, { credentials: "include" });
        if (!response.ok) {
          console.warn(
            `[Amazon Exporter] Invoice popover fetch failed for ${orderId}: HTTP ${response.status}`
          );
          return null;
        }
        const doc = new DOMParser().parseFromString(await response.text(), "text/html");
        return extractInvoicePdfHrefs(doc);
      },
      isStopRequested: () => stopRequested || !getExportState(),
      download: (data) => import_webextension_polyfill.default.runtime.sendMessage({ action: "downloadInvoiceUrl", data }),
      warn: (...args) => console.warn(...args)
    });
  }
  async function setDownloadsUIEnabled(enabled) {
    try {
      await import_webextension_polyfill.default.runtime.sendMessage({
        action: "setDownloadsUIEnabled",
        data: { enabled }
      });
    } catch (error) {
      console.warn("[Amazon Exporter] Failed to toggle downloads UI:", error);
    }
  }
  function extractInvoicePdfHrefs(doc) {
    const scope = doc.querySelector(".invoice-list") ?? doc;
    const hrefs = [];
    for (const a of scope.querySelectorAll("a[href]")) {
      const href = a.getAttribute("href") || "";
      if (isPdfInvoiceHref(href)) hrefs.push(href);
    }
    return hrefs;
  }
  function parseItemPricesFromDetails(order, doc) {
    const asinPriceMap = /* @__PURE__ */ new Map();
    const amount = getAmountPattern(order.currency);
    const itemContainers = doc.querySelectorAll(
      '.a-row, [class*="shipment-item"], [class*="od-shipment-item"], tr, .a-fixed-left-grid-inner'
    );
    itemContainers.forEach((container) => {
      const link = container.querySelector('a[href*="/dp/"], a[href*="/gp/product/"]');
      if (!link) return;
      const asinMatch = (link.getAttribute("href") || "").match(
        /\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i
      );
      if (!asinMatch?.[1]) return;
      const asin = asinMatch[1].toUpperCase();
      const text = container.textContent || "";
      const pricePatterns = [
        new RegExp(`${CURRENCY_TOKEN}\\s*(${amount})`, "gi"),
        new RegExp(`(${amount})\\s*(?:${CURRENCY_TOKEN}|\u5186)`, "gi")
      ];
      for (const pattern of pricePatterns) {
        const matches = text.matchAll(pattern);
        for (const match of matches) {
          if (match[1]) {
            const price = parsePrice(match[1]);
            if (price > 0) {
              if (!asinPriceMap.has(asin)) {
                asinPriceMap.set(asin, price);
              }
              break;
            }
          }
        }
        if (asinPriceMap.has(asin)) break;
      }
    });
    const orderSummary = doc.querySelector(
      '#orderSummary, .order-summary, [class*="order-summary"]'
    );
    if (orderSummary) {
      const summaryRows = orderSummary.querySelectorAll(".a-row, tr");
      summaryRows.forEach((row) => {
        const rowText = row.textContent || "";
        const discountMatch = rowText.match(
          new RegExp(
            `(Rabatt|Nachlass|Ersparnis|Discount|Coupon|\u5272\u5F15|\u30AF\u30FC\u30DD\u30F3)[:\uFF1A\\s]*-?\\s*${CURRENCY_TOKEN}?\\s*(${amount})`,
            "i"
          )
        );
        if (discountMatch?.[2]) {
          const discountAmount = parsePrice(discountMatch[2]);
          if (discountAmount > 0) {
            console.log(`[Amazon Exporter] Found discount in summary: ${discountAmount}`);
          }
        }
      });
    }
    order.items.forEach((item) => {
      const price = asinPriceMap.get(item.asin);
      if (price !== void 0) {
        item.price = price;
      }
    });
    const itemsWithoutPrice = order.items.filter((item) => item.price === 0);
    if (itemsWithoutPrice.length > 0) {
      const pageText = doc.body.textContent || "";
      itemsWithoutPrice.forEach((item) => {
        const asinRegex = new RegExp(`${item.asin}[^\u20AC\xA3$\xA5\uFFE5]*${CURRENCY_TOKEN}\\s*(${amount})`, "i");
        const match = pageText.match(asinRegex);
        if (match?.[1]) {
          const price = parsePrice(match[1]);
          if (price > 0) {
            item.price = price;
          }
        }
      });
    }
  }
  function parsePromotionsFromDetails(order, doc) {
    const promotions = [];
    let totalSavings = 0;
    const amount = getAmountPattern(order.currency);
    const promotionSelectors = [
      '[class*="promotion"]',
      '[class*="savings"]',
      '[class*="discount"]',
      '[class*="coupon"]',
      ".a-color-success",
      ".a-color-price"
    ];
    const checkedTexts = /* @__PURE__ */ new Set();
    promotionSelectors.forEach((selector) => {
      const elements = doc.querySelectorAll(selector);
      elements.forEach((el) => {
        const text = el.textContent?.trim() || "";
        if (checkedTexts.has(text)) return;
        checkedTexts.add(text);
        const savingsPatterns = [
          new RegExp(
            `(?:Rabatt|Nachlass|Ersparnis|Savings?|Discount|Gutschein|Coupon|Descuento|Ahorro|Cup[o\xF3]n|Promoci[o\xF3]n|\u5272\u5F15|\u30AF\u30FC\u30DD\u30F3)[:\uFF1A\\s]*-?\\s*${CURRENCY_TOKEN}?\\s*(${amount})`,
            "i"
          ),
          new RegExp(`-\\s*${CURRENCY_TOKEN}\\s*(${amount})`, "i"),
          new RegExp(`${CURRENCY_TOKEN}\\s*-\\s*(${amount})`, "i")
        ];
        for (const pattern of savingsPatterns) {
          const match = text.match(pattern);
          if (match?.[1]) {
            const amount2 = parsePrice(match[1]);
            if (amount2 > 0) {
              const description = text.replace(/\s+/g, " ").trim().substring(0, 100);
              if (!promotions.some(
                (p) => Math.abs(p.amount - amount2) < 0.01 && p.description === description
              )) {
                promotions.push({ description, amount: amount2 });
                totalSavings += amount2;
              }
              break;
            }
          }
        }
      });
    });
    const summarySection = doc.querySelector(
      '#orderSummary, .order-summary, [class*="order-summary"], .a-box.order-summary'
    );
    if (summarySection) {
      const rows = summarySection.querySelectorAll(".a-row, tr, div");
      rows.forEach((row) => {
        const text = row.textContent?.trim() || "";
        if (checkedTexts.has(text)) return;
        checkedTexts.add(text);
        if (/Rabatt|Nachlass|Ersparnis|Savings?|Discount|Gutschein|Coupon|Angebot|Descuento|Ahorro|Cup[oó]n|Promoci[oó]n|割引|クーポン/i.test(
          text
        )) {
          const amountMatch = text.match(
            new RegExp(`-?\\s*${CURRENCY_TOKEN}?\\s*(${amount})\\s*${CURRENCY_TOKEN}?`, "i")
          );
          if (amountMatch?.[1]) {
            const amount2 = parsePrice(amountMatch[1]);
            if (amount2 > 0) {
              const description = text.replace(/\s+/g, " ").trim().substring(0, 100);
              if (!promotions.some((p) => Math.abs(p.amount - amount2) < 0.01)) {
                promotions.push({ description, amount: amount2 });
                totalSavings += amount2;
              }
            }
          }
        }
      });
    }
    const itemsTotal = order.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
    if (itemsTotal > order.totalAmount && order.totalAmount > 0) {
      const unexplainedDiscount = Math.round((itemsTotal - order.totalAmount) * 100) / 100;
      if (unexplainedDiscount > totalSavings + 0.01) {
        const additionalDiscount = Math.round((unexplainedDiscount - totalSavings) * 100) / 100;
        if (additionalDiscount > 0.01) {
          promotions.push({
            description: getMessage("additionalDiscount"),
            amount: additionalDiscount
          });
          totalSavings = unexplainedDiscount;
        }
      }
    }
    order.promotions = promotions;
    order.totalSavings = Math.round(totalSavings * 100) / 100;
    if (promotions.length > 0) {
      console.log(
        `[Amazon Exporter] Order ${order.orderId} has ${promotions.length} promotions, total savings: \u20AC${totalSavings}`
      );
    }
  }
  function parsePaymentSummaryFromDetails(order, doc) {
    const chargeSummary = doc.querySelector('[data-component="chargeSummary"]');
    if (!chargeSummary) return;
    const rows = [];
    chargeSummary.querySelectorAll("li").forEach((li) => {
      const labelEl = li.querySelector(".od-line-item-row-label");
      const valueEl = li.querySelector(".od-line-item-row-content");
      const label = (labelEl?.textContent || "").replace(/\s+/g, " ").trim();
      const valueText = (valueEl?.textContent || "").replace(/\s+/g, " ").trim();
      if (!label || !valueText) return;
      const amount = parseCurrencyAmount(valueText);
      rows.push({ label, amount });
    });
    const { chargedAmount, giftCardAmount } = summarizePaymentRows(rows);
    order.chargedAmount = chargedAmount;
    order.giftCardAmount = giftCardAmount;
  }
  function convertToCSV(orders, includeTransactions) {
    return convertOrdersToCSV(orders, getMessage, includeTransactions);
  }
  function updateProgress(percent, message) {
    import_webextension_polyfill.default.runtime.sendMessage({
      action: "updateProgress",
      data: { percent, message }
    }).catch(() => {
    });
  }
})();
