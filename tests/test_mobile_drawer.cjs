const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('sidecar/static/app.js','utf8');
const listeners=new Map(),attrs=new Map();let active;
function element(id){const a=new Map();attrs.set(id,a);return {hidden:false,inert:false,setAttribute:(k,v)=>a.set(k,v),removeAttribute:k=>a.delete(k),addEventListener:(k,f)=>listeners.set(id+':'+k,f),focus(){active=this;},getClientRects:()=>[{}]};}
const ids=['tool-navigation','open-tool-menu','close-tool-menu','tool-menu-backdrop'];const elements=Object.fromEntries(ids.map(id=>[id,element(id)]));
const workspace=element('workspace'),bar=element('bar'),brand=element('brand'),tool=element('tool');
elements['tool-navigation'].querySelector=()=>tool;
elements['tool-navigation'].querySelectorAll=()=>[brand,elements['close-tool-menu'],tool];
const classes=new Set();let onResize;const media={matches:true,addEventListener:(name,fn)=>onResize=fn};
const context=vm.createContext({window:{matchMedia:()=>media},document:{querySelector:s=>s==='.workspace'?workspace:bar,body:{classList:{toggle:(key,on)=>on?classes.add(key):classes.delete(key)}},addEventListener:(name,fn)=>listeners.set('document:'+name,fn),get activeElement(){return active;}},$:id=>elements[id]});
vm.runInContext(source.slice(source.indexOf('(function initializeMobileDrawer(){')),context);
const click=id=>listeners.get(id+':click')();
assert(elements['tool-navigation'].inert);assert(elements['tool-menu-backdrop'].hidden);assert.equal(attrs.get('open-tool-menu').get('aria-expanded'),'false');
click('open-tool-menu');assert(classes.has('mobile-drawer-open'));assert.equal(active,elements['close-tool-menu']);assert(workspace.inert&&bar.inert);assert.equal(attrs.get('tool-navigation').get('aria-modal'),'true');
let prevented=false;const key=(key,shiftKey=false)=>listeners.get('document:keydown')({key,shiftKey,preventDefault(){prevented=true;}});
active=tool;key('Tab');assert.equal(active,brand);assert(prevented);active=brand;key('Tab',true);assert.equal(active,tool);
key('Escape');assert(!classes.size);assert.equal(active,elements['open-tool-menu']);assert(!workspace.inert&&!bar.inert);
for(const id of ['tool-menu-backdrop','close-tool-menu']){click('open-tool-menu');click(id);assert(!classes.size);}
click('open-tool-menu');listeners.get('tool-navigation:click')({target:{closest:()=>tool}});assert(!classes.size);
click('open-tool-menu');media.matches=false;onResize();assert(!classes.size);assert(!elements['tool-navigation'].inert);assert(!attrs.get('tool-navigation').has('aria-hidden'));assert(!attrs.get('tool-navigation').has('role'));assert(!workspace.inert&&!bar.inert);
click('open-tool-menu');assert(!classes.size,'Drawer cannot open on desktop');media.matches=true;onResize();assert(elements['tool-navigation'].inert);
console.log('Mobile drawer opening, dismissals, tool selection, focus trap, inert background and desktop resize reset passed.');
