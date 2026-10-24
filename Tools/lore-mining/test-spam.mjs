// node Tools/lore-mining/test-spam.mjs -> PASS spam or FAIL lines
import { isSpamText, isSpamLogin, filterSpam, STRONG_TLDS, WEAK_TLDS } from './spam.mjs';
import fs from 'fs';
let bad = 0; const C = (ok, m) => { if (!ok) { bad++; console.log('FAIL ' + m); } };
for (const l of ['succeedingsteelbqdzvkxr', 'dramaticlacencjhwz', 'auxiliarygamblingmtkxvs']) C(isSpamLogin(l), 'spam login ' + l);
for (const l of ['lvlmarshmello', 'snowyroses_', 'spongefredcircleshorts', 't1cklem0n3ter324', 'nxghtmare_rl_', 'penguinslittlebro', 'im_just_a_pineapple', 'carteriscool898', 'blizzyfvv', 'imnotmelloiswarghhh', 'xxxxlover4u2', 'darkwolf9x8y7z6w']) C(!isSpamLogin(l), 'real login ' + l);
for (const t of ['Best viewers with viewers streamboo .org', 'Ai vIewers streamboo . Com', 'cheap followers at foo.xyz', 'Ai viewers stre\u{1D4EA}mboo .com', 'Cheapest Viewers boosttask.ru', 'Top Viewers streamboo .com']) C(isSpamText(t), 'spam text ' + t);
C(isSpamText('hi check bar.com', true) && !isSpamText('hi check bar.com'), 'a link in a FIRST message is spam, later it is not');
for (const t of ['check google.com for the rank', 'how are the viewers today', 'yo peng', 'who tf is streamboo', 'peng put me on how do i get viewers like you bro?', 'it means when you start up stream you get viewers imeditaly', 'https://open.spotify.com/track/abc', 'https://clips.twitch.tv/x', 'youtu.be/abc', 'up.live idk', 'ok.me']) C(!isSpamText(t, true) || t.startsWith('check google'), 'not spam: ' + t);
const rows = [{ u: 'alice', x: 'hi' }, { u: 'bobspam', x: 'Best viewers with viewers streamboo .org' }, { u: 'alice', x: 'lol' }, { u: 'bobspam', x: 'hello' }, { u: 'carol', x: 'free followers at zzz.net' }, { u: 'dave', x: 'hey' }, { u: 'dave', x: 'see dave.com' }, { u: 'hijacked', x: 'yo' }, { u: 'hijacked', x: 'Ai viewers streamboo .com' }, { u: 'hijacked', x: 'back' }];
const f = filterSpam(rows);
C(f.users.has('bobspam') && f.users.has('carol') && !f.users.has('alice') && !f.users.has('dave') && !f.users.has('hijacked'), 'spam accounts: ' + [...f.users]);
C(f.droppedMessages === 1 && f.rows.filter(r => r.u === 'hijacked').length === 2 && !f.rows.some(r => r.u === 'bobspam'), 'a hijacked regular loses only the spam message');
// one shared TLD list: HostSpamFirst.cs == spam.mjs == HostWelcomeBack.cs
const arr = (file, name) => { const m = new RegExp(name + String.raw`\s*=\s*\{([^}]*)\}`).exec(fs.readFileSync(new URL(file, import.meta.url), 'utf8')); return m ? [...m[1].matchAll(/"([^"]+)"/g)].map(x => x[1]) : null; };
const sf = arr('../../PinguinoHost/HostSpamFirst.cs', 'Tlds'), ws = arr('../../PinguinoHost/HostWelcomeBack.cs', 'SpamTldsStrong'), ww = arr('../../PinguinoHost/HostWelcomeBack.cs', 'SpamTldsWeak');
const same = (a, b) => a && b && [...a].sort().join() === [...b].sort().join();
C(same(sf, [...STRONG_TLDS, ...WEAK_TLDS]), 'spam.mjs TLDs == HostSpamFirst.Tlds');
C(same(ws, STRONG_TLDS) && same(ww, WEAK_TLDS), 'HostWelcomeBack TLD lists == spam.mjs');
for (const t of ['cheap viewers at foo.io', 'cheap viewers at bar.gg', 'Best viewers streamboo .info']) C(isSpamText(t), 'spam text (more TLDs): ' + t);
for (const t of ['lol sure. to be fair', 'ok. us too', 'that was good. me too', 'peng. ai is wild']) C(!isSpamText(t, true), 'prose is not a domain: ' + t);
// a known regular whose first line of the day has a link is kept
const kr = filterSpam([{ u: 'regular', x: 'check clips.com' }, { u: 'newbie', x: 'check clips.com' }], new Set(['regular']));
C(!kr.users.has('regular') && kr.users.has('newbie'), 'known people keep their first-line link; unknown ones do not');
console.log(bad ? 'FAILED ' + bad : 'PASS spam'); process.exit(bad ? 1 : 0);
