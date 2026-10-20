import fs from 'fs';const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const pairs=JSON.parse(fs.readFileSync(S+'/pairs.json','utf8'));
const from=+process.argv[3],to=+process.argv[4];
let k=0;
for(const p of pairs.slice(from,to)){
  console.log('\n### '+p.a+' <-> '+p.b+' ('+p.ab+'/'+p.ba+')');
  const hits=msgs.filter(m=>((m.u===p.a&&new RegExp('@'+p.b,'i').test(m.x))||(m.u===p.b&&new RegExp('@'+p.a,'i').test(m.x)))&&m.x.length>25);
  const step=Math.max(1,Math.floor(hits.length/6));
  for(let i=0;i<hits.length&&i<6*step;i+=step)console.log(hits[i].d+' '+hits[i].u+': '+hits[i].x.replace(/@/g,'').slice(0,150));
}
