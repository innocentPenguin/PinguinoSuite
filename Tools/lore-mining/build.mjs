import fs from 'fs';import {NOTES,LORE} from './notes.mjs';
const S=process.argv[2];const OUT='D:/PinguinoSuite/Data/lore';fs.mkdirSync(OUT+'/person_cards',{recursive:true});
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const feat=JSON.parse(fs.readFileSync(S+'/feat.json','utf8'));
const pairs=JSON.parse(fs.readFileSync(S+'/pairs.json','utf8'));
const clusters=JSON.parse(fs.readFileSync(S+'/clusters.json','utf8'));
const alias=JSON.parse(fs.readFileSync('D:/PinguinoSuite/Data/boards/aliases.json','utf8')).aliases;
const mem=JSON.parse(fs.readFileSync('D:/PinguinoSuite/Data/runtime/chat_memory.json','utf8'));
const optOut=new Set();for(const v of Object.values(mem))if(v&&(v.Privacy==='anon'||v.Privacy==='forget')){optOut.add(String(v.Login).toLowerCase());for(const a of v.Aliases||[])optOut.add(String(a).toLowerCase())}
const readJ=p=>{try{return JSON.parse(fs.readFileSync(p,'utf8'))}catch{return null}};
const bots=new Set(['nightbot','streamelements','pinguinob0t','synchrabot','soundalerts','chattypinguino','pinguinohelper','rocketrankbot','potatbotat']);
const sensitive=/\b(mom|mother|dad|father|sister|brother|parents?|years? old|drugs?|weed|suicid|kill myself|depress\w*|anxiety|therap\w*|sex|dick|pussy|nude|naked|minor|cancer|died|funeral|address|phone|snap|insta|n[i1]gg\w*|fag\w*|retard\w*|rape)\b/i;
const clean=t=>!sensitive.test(t)&&!/https?:/.test(t);
const rev={};for(const [a,m] of Object.entries(alias))(rev[m]??=[]).push(a);
const months={};for(const m of msgs){const k=m.d.slice(0,7);(months[m.u]??={});months[m.u][k]=(months[m.u][k]||0)+1}
const hour=h=>{const c=(h+24-5)%24;return (c%12||12)+(c<12?'AM':'PM')};
const roast=/\b(stfu|sybau|shut up|dumb|idiot|trash|bad|ass|bum|buns|clown|cringe|loser|bozo|skill issue|ratio|washed|noob)\b/i;
const warm=/\b(thank|thanks|ty|love|ily|proud|gg|congrats|nice|good job|miss|welcome|cute|best|goat|appreciate)\b/i;
const game=/\b(rocket|rl|gc|ssl|rank|mmr|1v1|2v2|3v3|tourney|custom|minecraft|mc|bedrock|java|roblox|repo|peak|queue|lobby|team|tm8|match)\b/i;
const pairKey=(a,b)=>a<b?a+'|'+b:b+'|'+a;
const tone={};
for(const m of msgs){ if(bots.has(m.u))continue; const ts=[...new Set([...m.x.matchAll(/@([a-z0-9_]{3,25})/gi)].map(x=>x[1].toLowerCase()))];
  for(const t of ts){ if(t===m.u||bots.has(t))continue; const k=pairKey(m.u,t); const o=tone[k]??={r:0,w:0,g:0,n:0,ex:[]}; o.n++; if(roast.test(m.x))o.r++; if(warm.test(m.x))o.w++; if(game.test(m.x))o.g++; if(o.ex.length<3&&m.x.length>40&&clean(m.x)&&Math.random()<0.02)o.ex.push([m.d,m.u,m.x.replace(/@/g,'').slice(0,140)]); }}
const pairTag=o=>{ const n=o.n||1; const tags=[]; if(o.r/n>0.12)tags.push('roast/banter'); if(o.w/n>0.12)tags.push('warm/supportive'); if(o.g/n>0.3)tags.push('game partners'); if(!tags.length)tags.push('chat friends'); return tags; };
const notices=fs.readFileSync(S+'/notices.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const sup={};const bump=(u,k,n=1)=>{u=(alias[u.toLowerCase()]||u.toLowerCase());(sup[u]??={subs:0,gifts:0,raidsLed:0,raidViewers:0})[k]+=n};
for(const n of notices){let r;
 if(r=/^(\S+) is gifting (\d+) Tier/.exec(n.x))bump(r[1],'gifts',+r[2]);
 else if(r=/^(\S+) gifted a Tier/.exec(n.x))bump(r[1],'gifts',1);
 else if(r=/^(\S+) (just )?(re)?subscribed/.exec(n.x))bump(r[1],'subs',1);
 else if(r=/^(\d+) raiders from (\S+) have joined/.exec(n.x)){bump(r[2],'raidsLed',1);bump(r[2],'raidViewers',+r[1])}}
const display=readJ('D:/PinguinoSuite/Data/boards/names.json')||{};
const cards=[];const people=[];
const ids=Object.entries(feat).filter(([u,v])=>v.n>=150&&!bots.has(u)&&!optOut.has(u)&&u!=='innocentpenguin_').sort((a,b)=>b[1].n-a[1].n);
const clusterOf={};clusters.forEach((g,i)=>g.forEach(u=>clusterOf[u]=i));
const myPairs={};for(const p of pairs){ (myPairs[p.a]??=[]).push(p);(myPairs[p.b]??=[]).push(p) }
const eraOf=mm=>{const e=Object.entries(mm||{}).filter(x=>x[1]>=20).map(x=>x[0]).sort();return e.length?e[0]+' to '+e[e.length-1]:'sporadic'};
for(const [u,v] of ids){
  const prof=readJ('D:/PinguinoSuite/Data/profiles/'+u+'.json')||{};
  const note=NOTES[u]||null;
  const partners=(myPairs[u]||[]).filter(p=>!bots.has(p.a)&&!bots.has(p.b)&&p.a!=='innocentpenguin_'&&p.b!=='innocentpenguin_').sort((a,b)=>b.tot-a.tot).slice(0,8).map(p=>{const o=p.a===u?p.b:p.a;const t=tone[pairKey(u,o)]||{n:1,r:0,w:0,g:0};return {login:o,to:(p.a===u?p.ab:p.ba),from:(p.a===u?p.ba:p.ab),tags:pairTag(t)}});
  const label=(()=>{ if(note?.treatsIvan&&note.treatsIvan!=='n/a')return note.treatsIvan; const t=[];
    if(v.toIvan>=40){ if(v.tease>v.praise*1.5)t.push('mostly teasing/banter'); else if(v.praise>=v.tease)t.push('mostly supportive'); else t.push('mixed: banter and support'); if(v.insult>=3)t.push('a few harsh jabs, banter-level'); }
    else t.push('rarely addresses Ivan directly');
    return t.join('; ')+' (auto-read, '+(v.toIvan>=40?'enough':'thin')+' evidence)'; })();
  const evidence=v.ivSamples.filter(s=>clean(s[1])).slice(-4);
  const card={login:u,display:(display[u]?.name)||prof.name||u,aliasesMerged:rev[u]||[],era:eraOf(months[u]),messages:v.n,activeDays:v.days,firstSeenInLogs:v.first,lastSeenInLogs:v.last,
    roles:prof.roles?{mod:!!prof.roles.mod,vip:!!prof.roles.vip,sub:!!prof.roles.sub,subMonths:prof.roles.subMonths||0}:undefined,
    peakHoursCentral:v.peakHoursUTC.map(hour),style:{avgMsgLength:v.avgLen,questionRate:v.qRate,capsRate:v.capsRate,linkRate:v.linkRate},
    who:note?.who,vibe:note?.vibe,
    treatsIvan:{read:label,addressesIvanTimes:v.toIvan,per1000Messages:+(v.toIvan/v.n*1000).toFixed(1),praiseHits:v.praise,teaseHits:v.tease,harshHits:v.insult,evidence},
    likes:(note?.likes?.length?note.likes:(prof.likes||[]).slice(0,5).map(x=>x.what)),dislikes:(note?.dislikes?.length?note.dislikes:(prof.dislikes||[]).slice(0,4).map(x=>x.what)),
    nicknamesUsedByChat:prof.nicknames||[],topEmotes:v.topEmotes.map(e=>e[0]),topCommands:v.cmds.slice(0,4),
    support:sup[u]||{subs:0,gifts:0,raidsLed:0,raidViewers:0},relationships:partners,community:clusterOf[u]!==undefined?('group '+(clusterOf[u]+1)):'none',
    lore:note?.lore||[],confidence:note?'hand-read of sampled messages + stats':(v.n>=1000?'stats + keyword reads':'stats only (thin)'),
    guardrails:'Facts from chat logs only. No age, family, health or private-life inference. Private: not pushed to the site.'};
  fs.writeFileSync(OUT+'/person_cards/'+u+'.json',JSON.stringify(card,null,1));cards.push(card);people.push({login:u,msgs:v.n,era:card.era,group:card.community});
}
const nodeSet=new Set(cards.map(c=>c.login));
const edges=pairs.filter(p=>nodeSet.has(p.a)&&nodeSet.has(p.b)&&p.tot>=30).map(p=>({a:p.a,b:p.b,aToB:p.ab,bToA:p.ba,mutual:p.mutual,tags:pairTag(tone[pairKey(p.a,p.b)]||{n:1,r:0,w:0,g:0}),example:(tone[pairKey(p.a,p.b)]?.ex||[])[0]||null}));
const groupsOut=clusters.slice(0,8).map((g,i)=>({group:i+1,size:g.length,members:g.slice(0,40),eraGuess:(()=>{const mm={};for(const u of g.slice(0,10))for(const [k,c] of Object.entries(months[u]||{}))mm[k]=(mm[k]||0)+c;return eraOf(mm)})()}));
fs.writeFileSync(OUT+'/people_graph.json',JSON.stringify({built:new Date().toISOString(),source:'Data/chat_logs 2026-02-15..2026-10-20 (666,891 messages, 1,775 logins, aliases merged)',aliasesApplied:alias,nodes:people,edges,groups:groupsOut},null,1));
fs.writeFileSync(OUT+'/channel_lore.json',JSON.stringify({built:new Date().toISOString(),items:LORE,streamer:NOTES.streamer_note},null,1));
fs.writeFileSync(S+'/cards.json',JSON.stringify(cards));
console.log('cards',cards.length,'edges',edges.length,'groups',groupsOut.length);
