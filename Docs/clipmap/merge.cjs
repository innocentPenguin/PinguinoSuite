// Usage: node merge.cjs <commands.json> [--write]. Reads slice-a..d.md, appends clip URLs to viewer command descs.
const fs=require('fs');
const f=process.argv[2],write=process.argv.includes('--write');
const data=JSON.parse(fs.readFileSync(f,'utf8'));
const BLOCK=new Set(['!vhoggie','!snowy','!shadow','!kara','!koops']); // innuendo / unclear / low
const ok=s=>/\b(solid|good|high|medium)\b/i.test(s)&&!/\b(loose|low)\b/i.test(s);
const picks={};
for(const x of 'abcd'){
  const p=__dirname+'/slice-'+x+'.md';if(!fs.existsSync(p))continue;
  for(const line of fs.readFileSync(p,'utf8').split(/\r?\n/)){
    if(!line.startsWith('|'))continue;
    const c=line.split('|').map(s=>s.trim());
    const url=(line.match(/https:\/\/www\.twitch\.tv\/innocentpenguin_\/clip\/[A-Za-z0-9_-]+/)||[])[0];
    if(!url)continue;
    const cmds=c[1].split('/').map(s=>s.trim()).filter(s=>s.startsWith('!')||/^[a-z]+$/i.test(s));
    const rest=c.slice(3).join(' ');
    if(!ok(rest))continue;
    for(const m of cmds)if(!BLOCK.has(m)&&!picks[m])picks[m]=url;
  }
}
let n=0;const done=[];
for(const e of data.viewer||[]){
  const url=picks[e.cmd]||picks[e.cmd.replace(/^!/,'')];
  if(!url||/clip|medal/i.test(e.desc||''))continue;
  e.desc=(e.desc||'')+' '+url;n++;done.push(e.cmd);
}
console.log(n,'linked:',done.join(' '));
if(write)fs.writeFileSync(f,JSON.stringify(data,null,1).replace(/\n/g,'\n'));
