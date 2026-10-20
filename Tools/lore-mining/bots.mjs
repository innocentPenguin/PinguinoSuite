import fs from 'fs';const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const botnames=['pinguinob0t','chattypinguino','pinguinohelper','nightbot','streamelements','soundalerts','synchrabot','rocketrankbot','potatbotat'];
const cnt={};for(const m of msgs)if(botnames.includes(m.u))cnt[m.u]=(cnt[m.u]||0)+1;console.log('bot msgs',cnt);
const firstSeen={};for(const m of msgs)if(botnames.includes(m.u)&&!firstSeen[m.u])firstSeen[m.u]=m.d;console.log('first',firstSeen);
const cmd={},cmd30={};for(const m of msgs){if(!m.x.startsWith('!')||botnames.includes(m.u))continue;const c=m.x.split(/\s+/)[0].toLowerCase();cmd[c]=(cmd[c]||0)+1;if(m.d>='2026-09-20')cmd30[c]=(cmd30[c]||0)+1}
const top=o=>Object.entries(o).sort((a,b)=>b[1]-a[1]).slice(0,45).map(e=>e.join(':')).join(' ');
console.log('ALL',top(cmd));console.log('LAST30',top(cmd30));
// addressed to bots
const re=/@?(pinguinob0t|pinguinobot|pinguinbot|chattypinguino|chatty|pinguinohelper|pinguino helper|helper)\b/i;
const addr={};let sample={};
for(const m of msgs){if(botnames.includes(m.u))continue;const r=re.exec(m.x);if(r){const k=r[1].toLowerCase();addr[k]=(addr[k]||0)+1;(sample[k]??=[]).push(m)}}
console.log(addr);
for(const k of Object.keys(sample)){const a=sample[k];console.log('\n>> '+k);for(let i=0;i<a.length;i+=Math.max(1,Math.floor(a.length/14)))console.log(a[i].d+' '+a[i].u+': '+a[i].x.slice(0,140))}
