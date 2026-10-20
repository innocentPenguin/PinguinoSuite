import fs from 'fs';
const S=process.argv[2];
const al=JSON.parse(fs.readFileSync('D:/PinguinoSuite/Data/boards/aliases.json','utf8')).aliases;
const main=u=>al[u]||u;
const toUtc=(d,t)=>new Date(d+'T'+t+'-05:00').getTime();
const lo=Date.parse('2026-02-15T00:00:00Z'),hi=Date.parse('2026-10-19T21:26:00Z');
const sb={};for(const l of fs.readFileSync(S+'/sb_msgs.tsv','utf8').split('\n')){if(!l)continue;const [d,t,u]=l.split('\t');const ts=toUtc(d,t);if(ts<lo||ts>hi)continue;const k=main(u);sb[k]=(sb[k]||0)+1}
const site={};for(const l of fs.readFileSync(S+'/msgs.raw.jsonl','utf8').split('\n')){const m=JSON.parse(l);const ts=Date.parse(m.d+'T'+m.t+'Z');if(ts<lo||ts>hi)continue;const k=main(m.u);site[k]=(site[k]||0)+1}
let a=0,b=0;for(const k in sb){a+=sb[k]}for(const k in site){b+=site[k]}console.log('SB',a,'site',b);
const rows=Object.keys({...sb,...site}).map(k=>({u:k,sb:sb[k]||0,site:site[k]||0})).filter(r=>r.sb>=300||r.site>=300);
rows.forEach(r=>r.diff=r.sb-r.site);
console.log('\nBiggest SB>site (site is missing messages):');
console.log(rows.sort((x,y)=>y.diff-x.diff).slice(0,15).map(r=>`${r.u} sb=${r.sb} site=${r.site} diff=${r.diff}`).join('\n'));
console.log('\nBiggest site>SB:');
console.log(rows.sort((x,y)=>x.diff-y.diff).slice(0,10).map(r=>`${r.u} sb=${r.sb} site=${r.site} diff=${r.diff}`).join('\n'));
const mid=rows.filter(r=>r.u!=='lvlmarshmello'&&r.site>=1000);const ratio=mid.map(r=>r.sb/r.site).sort((x,y)=>x-y);console.log('\nratio sb/site among 1000+ users: median',ratio[Math.floor(ratio.length/2)].toFixed(3),'p10',ratio[Math.floor(ratio.length*.1)].toFixed(3),'p90',ratio[Math.floor(ratio.length*.9)].toFixed(3));
fs.writeFileSync(S+'/cal.json',JSON.stringify(rows));
