import {build} from 'esbuild';
import {mkdirSync,cpSync} from 'node:fs';
const out='../../sidecar/amazon-extension';mkdirSync(out,{recursive:true});
await build({entryPoints:{content:'vendor/src/content/content.ts',background:'background.js',popup:'popup.js',ready:'ready.js'},outdir:out,bundle:true,format:'esm',target:'chrome120'});
for(const file of ['popup.html','manifest.json'])cpSync(file,out+'/'+file);
cpSync('vendor/src/_locales',out+'/_locales',{recursive:true});

cpSync('vendor/LICENSE',out+'/EXPORTER-LICENSE');
cpSync('node_modules/webextension-polyfill/LICENSE',out+'/POLYFILL-LICENSE');
