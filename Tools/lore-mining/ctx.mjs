import fs from 'fs';const S=process.argv[2];const terms=process.argv.slice(3);
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
for(const t of terms){const re=new RegExp('(^|[^a-z0-9])'+t+'([^a-z0-9]|$)','i');const hit=[];msgs.forEach((m,i)=>{if(re.test(m.x)&&m.u!=='nightbot')hit.push(i)});
 console.log('\n=== '+t+' ('+hit.length+')');
 const pick=[0,1,Math.floor(hit.length*.25),Math.floor(hit.length*.5),Math.floor(hit.length*.75),hit.length-2,hit.length-1].filter((v,i,a)=>v>=0&&a.indexOf(v)===i);
 for(const p of pick){const i=hit[p];if(i==null)continue;for(let j=Math.max(0,i-1);j<=Math.min(msgs.length-1,i+1);j++)console.log(msgs[j].d,msgs[j].u+': '+msgs[j].x.slice(0,160));console.log('-')}
}
