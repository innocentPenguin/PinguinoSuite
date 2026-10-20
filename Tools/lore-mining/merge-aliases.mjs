// folds Data\boards\aliases.json into msgs.jsonl (keeps msgs.raw.jsonl). usage: node merge-aliases.mjs <workdir>
import fs from 'fs';const S=process.argv[2];
const al=JSON.parse(fs.readFileSync('D:/PinguinoSuite/Data/boards/aliases.json','utf8')).aliases;
if(!fs.existsSync(S+'/msgs.raw.jsonl'))fs.copyFileSync(S+'/msgs.jsonl',S+'/msgs.raw.jsonl');
const out=fs.readFileSync(S+'/msgs.raw.jsonl','utf8').split('\n').map(l=>{const o=JSON.parse(l);if(al[o.u])o.u=al[o.u];o.x=o.x.replace(/@([A-Za-z0-9_]{3,25})/g,(s,n)=>al[n.toLowerCase()]?'@'+al[n.toLowerCase()]:s);return JSON.stringify(o)});
fs.writeFileSync(S+'/msgs.jsonl',out.join('\n'));
