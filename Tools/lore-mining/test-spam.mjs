// node Tools/lore-mining/test-spam.mjs -> PASS spam or FAIL lines
import { isSpamText, isSpamLogin, filterSpam } from './spam.mjs';
let bad = 0; const C = (ok, m) => { if (!ok) { bad++; console.log('FAIL ' + m); } };
for (const l of ['succeedingsteelbqdzvkxr', 'dramaticlacencjhwz', 'auxiliarygamblingmtkxvs', 'goddambalance2g3l2']) C(isSpamLogin(l), 'spam login ' + l);
for (const l of ['lvlmarshmello', 'snowyroses_', 'spongefredcircleshorts', 't1cklem0n3ter324', 'nxghtmare_rl_', 'penguinslittlebro', 'im_just_a_pineapple', 'carteriscool898', 'blizzyfvv', 'imnotmelloiswarghhh']) C(!isSpamLogin(l), 'real login ' + l);
for (const t of ['Best viewers with viewers streamboo .org', 'Ai vIewers streamboo . Com', 'cheap followers at foo.xyz', 'Ai viewers stre\u{1D4EA}mboo .com', 'Cheapest Viewers boosttask.ru', 'Top Viewers streamboo .com']) C(isSpamText(t), 'spam text ' + t);
C(isSpamText('hi check bar.com', true) && !isSpamText('hi check bar.com'), 'a link in a FIRST message is spam, later it is not');
for (const t of ['check google.com for the rank', 'how are the viewers today', 'yo peng', 'who tf is streamboo', 'peng put me on how do i get viewers like you bro?', 'it means when you start up stream you get viewers imeditaly', 'https://open.spotify.com/track/abc', 'https://clips.twitch.tv/x', 'youtu.be/abc', 'up.live idk', 'ok.me']) C(!isSpamText(t, true) || t.startsWith('check google'), 'not spam: ' + t);
const rows = [{ u: 'alice', x: 'hi' }, { u: 'bobspam', x: 'Best viewers with viewers streamboo .org' }, { u: 'alice', x: 'lol' }, { u: 'bobspam', x: 'hello' }, { u: 'carol', x: 'free followers at zzz.net' }, { u: 'dave', x: 'hey' }, { u: 'dave', x: 'see dave.com' }, { u: 'hijacked', x: 'yo' }, { u: 'hijacked', x: 'Ai viewers streamboo .com' }, { u: 'hijacked', x: 'back' }];
const f = filterSpam(rows);
C(f.users.has('bobspam') && f.users.has('carol') && !f.users.has('alice') && !f.users.has('dave') && !f.users.has('hijacked'), 'spam accounts: ' + [...f.users]);
C(f.droppedMessages === 1 && f.rows.filter(r => r.u === 'hijacked').length === 2 && !f.rows.some(r => r.u === 'bobspam'), 'a hijacked regular loses only the spam message');
console.log(bad ? 'FAILED ' + bad : 'PASS spam'); process.exit(bad ? 1 : 0);
