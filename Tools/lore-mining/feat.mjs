import fs from 'fs';const S=process.argv[2];
const msgs=fs.readFileSync(S+'/msgs.jsonl','utf8').split('\n').map(l=>JSON.parse(l));
const bots=new Set(['nightbot','streamelements','pinguinob0t','synchrabot','soundalerts','chattypinguino','pinguinohelper','rocketrankbot','potatbotat','moobot','fossabot','wizebot','streamlabs','sery_bot','commanderroot']);
const toIvan=/(\bpeng\b|\bpengu\b|\bpenguin\b|\bpinguino\b|@innocentpenguin_|\bpingu\b|\bpenguino\b)/i;
const praise=/\b(goat|goated|best|love you|love u|ily|w streamer|w stream|good stream|great stream|legend|king|cracked|insane|clean|nice|goated|goat|peak|cooking|proud|appreciate|thank you|thanks|thx|ty |gg|W\b|goated|pog|poggers|amazing|awesome|hilarious|funny)\b/i;
const tease=/\b(lol|lmao|lmfao|bro|bruh|clown|trash|bad|washed|ass|mid|noob|cooked|sus|cap|nah|delulu|skill issue|ratio|lil bro|dumb|stupid|silly|goofy)\b/i;
const insult=/\b(fuck you|stfu|shut up|shut the fuck|hate you|you suck|you're trash|youre trash|bozo|idiot|loser|garbage streamer|worst streamer|ruined|annoying|cringe)\b/i;
const U={};const get=u=>U[u]||(U[u]={n:0,days:new Set(),first:null,last:null,hours:{},toIvan:0,praise:0,tease:0,insult:0,ivSamples:[],words:{},emotes:{},q:0,cmds:{},likes:[],dislikes:[],links:0,caps:0,len:0});
const likeRe=/\b(i (really )?(love|like|enjoy|prefer|main|play)|my (fav|favorite|favourite)|i('m| am) (a fan of|obsessed with|addicted to)|best (game|song|car|rank|team)|i fucking love)\b[^.!?]{3,90}/i;
const dislikeRe=/\b(i (really )?(hate|dislike|can'?t stand|cant stand|despise)|(is|are) (so )?(trash|overrated|annoying)|worst (game|part|thing|player)|i don'?t like|i dont like|not a fan of)\b[^.!?]{2,90}/i;
const stop=new Set('the a an and or but to of in on for with is are was were it its i you he she we they me my your this that so just not be have has had do does did at as if from by what when who how why can will would should could im dont its thats u ur lol yeah yes no ok oh like get got go going one all out up there here been more about than then them him her his their our us very really too also some any now still back off too much even into over only same new good bad'.split(' '));
const emoteRe=/\b([a-z]{3,10}[A-Z0-9][A-Za-z0-9]{2,})\b/g; // camel-ish emotes e.g. innoce108Eepy
let prevByUser={};
for(const m of msgs){ if(bots.has(m.u))continue; const u=get(m.u); u.n++; u.days.add(m.d); u.first??=m.d;u.last=m.d; const h=+m.t.slice(0,2);u.hours[h]=(u.hours[h]||0)+1;
  u.len+=m.x.length; if(m.x.startsWith('!')){const c=m.x.split(' ')[0].toLowerCase();u.cmds[c]=(u.cmds[c]||0)+1;continue;}
  if(/https?:\/\//.test(m.x))u.links++; if(m.x.length>8&&m.x===m.x.toUpperCase()&&/[A-Z]/.test(m.x))u.caps++;
  if(/\?$/.test(m.x))u.q++;
  for(const e of m.x.matchAll(emoteRe))u.emotes[e[1]]=(u.emotes[e[1]]||0)+1;
  if(m.u!=='innocentpenguin_'&&toIvan.test(m.x)){u.toIvan++;if(praise.test(m.x))u.praise++;if(tease.test(m.x))u.tease++;if(insult.test(m.x))u.insult++;
    if(u.ivSamples.length<400)u.ivSamples.push([m.d,m.x.slice(0,200)]);}
  let r=likeRe.exec(m.x);if(r&&u.likes.length<12)u.likes.push([m.d,m.x.slice(0,160)]);
  r=dislikeRe.exec(m.x);if(r&&u.dislikes.length<12)u.dislikes.push([m.d,m.x.slice(0,160)]);
  for(const w of m.x.toLowerCase().replace(/[^a-z' ]/g,' ').split(/\s+/)){if(w.length<3||stop.has(w))continue;u.words[w]=(u.words[w]||0)+1}
}
const out={};
for(const [k,v] of Object.entries(U)){ if(v.n<30)continue;
  out[k]={n:v.n,days:v.days.size,first:v.first,last:v.last,avgLen:Math.round(v.len/v.n),qRate:+(v.q/v.n).toFixed(3),capsRate:+(v.caps/v.n).toFixed(3),linkRate:+(v.links/v.n).toFixed(3),
   peakHoursUTC:Object.entries(v.hours).sort((a,b)=>b[1]-a[1]).slice(0,3).map(e=>+e[0]),
   cmds:Object.entries(v.cmds).sort((a,b)=>b[1]-a[1]).slice(0,6),
   toIvan:v.toIvan,praise:v.praise,tease:v.tease,insult:v.insult,ivSamples:v.ivSamples.slice(-6),
   topEmotes:Object.entries(v.emotes).sort((a,b)=>b[1]-a[1]).slice(0,5),
   topWords:Object.entries(v.words).sort((a,b)=>b[1]-a[1]).slice(0,12).map(e=>e[0]),likes:v.likes.slice(0,6),dislikes:v.dislikes.slice(0,6)};}
fs.writeFileSync(S+'/feat.json',JSON.stringify(out));
console.log(Object.keys(out).length,'users with >=30 msgs');
const top=Object.entries(out).sort((a,b)=>b[1].n-a[1].n).slice(0,5).map(([k,v])=>[k,v.toIvan,v.praise,v.tease,v.insult]);console.log(top);
const ins=Object.entries(out).filter(([k,v])=>v.insult>=3).sort((a,b)=>b[1].insult-a[1].insult).slice(0,15).map(([k,v])=>k+':'+v.insult+'/'+v.toIvan);console.log('insult>=3:',ins.join(' '));
