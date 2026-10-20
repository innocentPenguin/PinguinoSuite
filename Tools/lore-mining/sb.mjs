// Count chat messages per user from the Streamer.bot debug logs (one "Queueing 'chat' ... TwitchChatMessage" line per message).
import {execSync,spawn} from 'child_process';import fs from 'fs';import readline from 'readline';
const ZIP='D:/PinguinoSuite/Archive/streamerbot-2026-10-19/logs.zip';
const S=process.argv[2];
const names=execSync(`unzip -Z1 "${ZIP}"`,{maxBuffer:1e8}).toString().split(/\r?\n/).filter(n=>/^log_2026\d{4}\.log$/.test(n)||/^log_20251\d{3}\.log$/.test(n));
const out=fs.createWriteStream(S+'/sb_msgs.tsv');
const re=/^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\.\d+ DBG\] ActionDispatcher :: Queueing 'chat' \(2cca2414-0a7e-4176-81e6-959fc474b8af, TwitchChatMessage\).*initiated by (\S+) with/;
let total=0;
for(const n of names){
  await new Promise(res=>{
    const p=spawn('unzip',['-p',ZIP,n]);const rl=readline.createInterface({input:p.stdout,crlfDelay:Infinity});let c=0;
    rl.on('line',l=>{if(l.indexOf('TwitchChatMessage')<0)return;const m=re.exec(l);if(m){out.write(m[1]+'\t'+m[2]+'\t'+m[3].toLowerCase()+'\n');c++}});
    rl.on('close',()=>{total+=c;console.log(n,c);res()});
  });
}
out.end();console.log('total',total);
