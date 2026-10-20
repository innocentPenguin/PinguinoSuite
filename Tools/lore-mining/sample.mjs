import fs from 'fs';const S=process.argv[2];const users=process.argv.slice(3);
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
let seed=11;const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647;
for(const u of users){
  const mine=msgs.filter(m=>m.u===u&&!m.x.startsWith('!')&&m.x.length>35&&!/https?:/.test(m.x));
  const first=msgs.find(m=>m.u===u);
  console.log('\n## '+u+' ('+mine.length+' long msgs; first '+first.d+')');
  const picks=new Set();while(picks.size<Math.min(11,mine.length))picks.add(Math.floor(rnd()*mine.length));
  [...picks].sort((a,b)=>a-b).forEach(i=>console.log(mine[i].d.slice(5)+' '+mine[i].x.slice(0,150)));
  const like=mine.filter(m=>/\b(peng|penguin)\b/i.test(m.x)&&/(love|hate|best|worst|thank|sorry|goat|trash|bad|good|funny|annoying|scam|ego|cringe|respect|proud|mom|mod|vip|unmod|ban|timeout)/i.test(m.x));
  for(const m of like.slice(-3))console.log('  >>PENG '+m.d.slice(5)+' '+m.x.slice(0,150));
}
