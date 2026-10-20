import fs from 'fs';
const S=process.argv[2];
const OUT='D:/PinguinoSuite/Data/chat_logs/sidecar';fs.mkdirSync(OUT,{recursive:true});
// America/Chicago local -> UTC, DST aware
const fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
function offsetMin(utcMs){const p=Object.fromEntries(fmt.formatToParts(new Date(utcMs)).map(x=>[x.type,x.value]));const asUtc=Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second);return (asUtc-utcMs)/60000}
function localToUtc(d,t){const [Y,M,D]=d.split('-').map(Number),[h,m,s]=t.split(':').map(Number);const guess=Date.UTC(Y,M-1,D,h,m,s);let off=offsetMin(guess);let u=guess-off*60000;off=offsetMin(u);return guess-off*60000}
const sb={};let n=0,first=null,last=null;
for(const l of fs.readFileSync(S+'/sb_msgs.tsv','utf8').split('\n')){if(!l)continue;const [d,t,u]=l.split('\t');if(u==='anonymous')continue;const ms=localToUtc(d,t);const iso=new Date(ms).toISOString();const day=iso.slice(0,10);(sb[u]??={})[day]=(sb[u][day]||0)+1;n++;if(!first||iso<first)first=iso;if(!last||iso>last)last=iso}
fs.writeFileSync(OUT+'/streamerbot_daily_counts.json',JSON.stringify({source:'Archive/streamerbot-2026-10-19/logs.zip: one "Queueing chat TwitchChatMessage" line per chat message; counts only, no text',days:'UTC',range:[first,last],messages:n,users:Object.keys(sb).length,counts:sb}));
console.log('sb',n,first,last,Object.keys(sb).length);
// site daily
const al=JSON.parse(fs.readFileSync('D:/PinguinoSuite/Data/boards/aliases.json','utf8')).aliases;const main=u=>al[u]||u;
const site={};for(const l of fs.readFileSync(S+'/msgs.raw.jsonl','utf8').split('\n')){const m=JSON.parse(l);(site[m.u]??={})[m.d]=(site[m.u][m.d]||0)+1}
// merge per (user,day)=max, then fold aliases
const tot={},totSite={},monthly={};
const users=new Set([...Object.keys(sb),...Object.keys(site)]);
for(const u of users){const days=new Set([...Object.keys(sb[u]||{}),...Object.keys(site[u]||{})]);const k=main(u);
  for(const d of days){const a=(site[u]||{})[d]||0,b=(sb[u]||{})[d]||0;const v=Math.max(a,b);tot[k]=(tot[k]||0)+v;totSite[k]=(totSite[k]||0)+a;const mo=d.slice(0,7);(monthly[k]??={})[mo]=(monthly[k][mo]||0)+v}}
const rows=Object.keys(tot).map(u=>({u,merged:tot[u],siteOnly:totSite[u]||0,gain:tot[u]-(totSite[u]||0)})).sort((a,b)=>b.merged-a.merged);
console.log(rows.slice(0,15).map(r=>`${r.u} merged=${r.merged} siteOnly=${r.siteOnly} +${r.gain}`).join('\n'));
fs.writeFileSync(OUT+'/message_totals_merged.json',JSON.stringify({rule:'per user per UTC day = max(public log sites, Streamer.bot logs); aliases folded; own Host recorder to be added by the Host after 2026-10-19',totals:Object.fromEntries(rows.map(r=>[r.u,{messages:r.merged,siteOnly:r.siteOnly}])),monthly},null,0));
console.log('marsh monthly',JSON.stringify(monthly['lvlmarshmello']));
console.log('rose monthly',JSON.stringify(monthly['snowyroses_']));
