import fs from 'fs';const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const feat=JSON.parse(fs.readFileSync(S+'/feat.json','utf8'));
const users=Object.keys(feat).filter(u=>feat[u].n>=300);
const days={},bi=Object.create(null);
for(const m of msgs){if(!feat[m.u]||feat[m.u].n<300)continue;(days[m.u]??=new Set()).add(m.d);
  if(m.x.startsWith('!')||/https?:/.test(m.x))continue;const w=m.x.toLowerCase().replace(/[^a-z' ]/g,' ').split(/\s+/).filter(x=>x.length>1);
  const v=bi[m.u]??=Object.create(null);for(let i=0;i<w.length;i++){const g=i<w.length-1?w[i]+' '+w[i+1]:null;v[w[i]]=(v[w[i]]||0)+1;if(g)v[g]=(v[g]||0)+1}}
const norm={};for(const u of users){const v=bi[u]||{};let s=0;for(const k in v)s+=v[k]*v[k];norm[u]=Math.sqrt(s)||1}
const res=[];
for(let i=0;i<users.length;i++)for(let j=i+1;j<users.length;j++){const a=users[i],b=users[j];
 const A=bi[a]||{},B=bi[b]||{};let dot=0;const [s,l]=Object.keys(A).length<Object.keys(B).length?[A,B]:[B,A];for(const k in s)if(l[k])dot+=s[k]*l[k];
 const cos=dot/(norm[a]*norm[b]);if(cos<0.55)continue;
 let ov=0;for(const d of days[a])if(days[b].has(d))ov++;const ovr=ov/Math.min(days[a].size,days[b].size);
 res.push({a,b,cos:+cos.toFixed(2),overlapDays:ov,overlapRatio:+ovr.toFixed(2),aSpan:feat[a].first+'..'+feat[a].last,bSpan:feat[b].first+'..'+feat[b].last});}
res.sort((x,y)=>y.cos-x.cos);
fs.writeFileSync(S+'/alias_cands.json',JSON.stringify(res));
console.log(res.slice(0,30).map(r=>`${r.a} ~ ${r.b} cos=${r.cos} overlapDays=${r.overlapDays} (${r.overlapRatio}) ${r.aSpan} | ${r.bSpan}`).join('\n'));
