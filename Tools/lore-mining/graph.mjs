import fs from 'fs';
const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const bots=new Set(['nightbot','streamelements','pinguinob0t','synchrabot','soundalerts','chattypinguino','pinguinohelper','moobot','fossabot','wizebot','sery_bot','streamlabs']);
const ivan='innocentpenguin_';
const users={}; const U=u=>users[u]||(users[u]={n:0,days:new Set(),first:null,last:null,out:{},inn:{},toIvan:0,fromIvan:0,ivanMentions:0,samples:[]});
const known=new Set(msgs.map(m=>m.u));
// directed mentions
const mre=/@([a-z0-9_]{3,25})/gi;
let prev=null;
for(const m of msgs){
  const u=U(m.u); u.n++; u.days.add(m.d); u.first??=m.d; u.last=m.d;
  const seen=new Set();
  for(const x of m.x.matchAll(mre)){ let t=x[1].toLowerCase(); if(t===m.u||seen.has(t))continue; seen.add(t);
    if(!known.has(t))continue;
    u.out[t]=(u.out[t]||0)+1; U(t).inn[m.u]=(U(t).inn[m.u]||0)+1; }
  // bare name mention of ivan
  if(m.u!==ivan && /\b(peng|pengu|penguin|pinguino|pingu)\b/i.test(m.x)) u.ivanMentions++;
}
const rows=Object.entries(users).filter(([k])=>!bots.has(k)).map(([k,v])=>({u:k,n:v.n,days:v.days.size,first:v.first,last:v.last,
  out:Object.entries(v.out).sort((a,b)=>b[1]-a[1]).slice(0,8),inn:Object.entries(v.inn).sort((a,b)=>b[1]-a[1]).slice(0,8),ivanMentions:v.ivanMentions}));
fs.writeFileSync(S+'/rows.json',JSON.stringify(rows));
// pair strengths (mutual)
const pairs={};
for(const [a,v] of Object.entries(users)){ if(bots.has(a))continue; for(const [b,c] of Object.entries(v.out)){ if(bots.has(b))continue; const k=[a,b].sort().join('|'); const p=pairs[k]||(pairs[k]={a:[a,b].sort()[0],b:[a,b].sort()[1],ab:0,ba:0}); if(a===p.a)p.ab+=c;else p.ba+=c; }}
const pl=Object.values(pairs).map(p=>({...p,tot:p.ab+p.ba,mutual:Math.min(p.ab,p.ba)})).sort((x,y)=>y.tot-x.tot);
fs.writeFileSync(S+'/pairs.json',JSON.stringify(pl));
console.log(pl.length,'pairs'); console.log(pl.slice(0,40).map(p=>`${p.a}<->${p.b} ${p.ab}/${p.ba}`).join('\n'));
