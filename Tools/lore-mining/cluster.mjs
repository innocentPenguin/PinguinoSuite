import fs from 'fs';const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const feat=JSON.parse(fs.readFileSync(S+'/feat.json','utf8'));
const pairs=JSON.parse(fs.readFileSync(S+'/pairs.json','utf8'));
// adjacency (weights = mentions both ways + adjacent-reply proximity)
const adj={};const add=(a,b,w)=>{(adj[a]??={})[b]=(adj[a][b]||0)+w;(adj[b]??={})[a]=(adj[b][a]||0)+w};
for(const p of pairs){ if(!feat[p.a]||!feat[p.b])continue; if(p.tot<15)continue; add(p.a,p.b,p.tot+2*p.mutual);}
const deg={};for(const a in adj)deg[a]=Object.values(adj[a]).reduce((x,y)=>x+y,0);
for(const a in adj)for(const b in adj[a])adj[a][b]=adj[a][b]/Math.sqrt(deg[a]*deg[b]); 
// label propagation
let label={};Object.keys(adj).forEach(k=>label[k]=k);
const nodes=Object.keys(adj);let seed=7;const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647;
for(let it=0;it<25;it++){nodes.sort(()=>rnd()-.5);for(const n of nodes){const sc={};for(const [m,w] of Object.entries(adj[n]))sc[label[m]]=(sc[label[m]]||0)+w;const best=Object.entries(sc).sort((a,b)=>b[1]-a[1])[0];if(best)label[n]=best[0]}}
const groups={};for(const n of nodes)(groups[label[n]]??=[]).push(n);
const out=Object.values(groups).filter(g=>g.length>=3).map(g=>g.sort((a,b)=>feat[b].n-feat[a].n)).sort((a,b)=>b.length-a.length);
fs.writeFileSync(S+'/clusters.json',JSON.stringify(out));
for(const g of out.slice(0,14))console.log(g.length+': '+g.slice(0,16).join(', '));
