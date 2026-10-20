import fs from 'fs'; import path from 'path';
const root='D:/PinguinoSuite/Data/chat_logs/2026'; const out=[]; const notices=[];
for(const m of fs.readdirSync(root).sort()) for(const f of fs.readdirSync(path.join(root,m)).sort()){
  const day=f.slice(0,10);
  for(const line of fs.readFileSync(path.join(root,m,f),'utf8').split(/\r?\n/)){
    let r=/^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\] #\S+ (\S+?): (.*)$/.exec(line);
    if(r){out.push({d:r[1],t:r[2],u:r[3].toLowerCase(),x:r[4]});continue;}
    r=/^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\] #\S+ \* (.*)$/.exec(line);
    if(r) notices.push({d:r[1],t:r[2],x:r[3]});
  }}
const S=process.argv[2];
fs.writeFileSync(S+'/msgs.jsonl',out.map(o=>JSON.stringify(o)).join('\n'));
fs.writeFileSync(S+'/notices.jsonl',notices.map(o=>JSON.stringify(o)).join('\n'));
console.log(out.length,notices.length);
const c={};for(const o of out)c[o.u]=(c[o.u]||0)+1;
console.log(Object.keys(c).length,'users'); console.log(Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,60).map(e=>e.join(':')).join(' '));
