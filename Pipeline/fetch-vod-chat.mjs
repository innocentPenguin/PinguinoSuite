// SECOND CHOICE. For chat logs use Pipeline/fetch-chat-logs.mjs (public log site, back to 2026-07-19, no extra tools). THIS script is still useful for
//   node Pipeline/fetch-vod-chat.mjs --history   (stream titles of every VOD -> the bot's stream history, no downloads)
// and, with TwitchDownloaderCLI installed, for downloading VOD chat:
// Downloads the chat of the channel's past streams (VODs) into the chat bot's archive folder, so the bot can search it.
//
//   node Pipeline\fetch-vod-chat.mjs                      every VOD Twitch still has (new ones only; already downloaded VODs are skipped)
//   node Pipeline\fetch-vod-chat.mjs --since 2026-10-01   only VODs from that date on
//   node Pipeline\fetch-vod-chat.mjs --list               just list the VODs (date, id, length, title), download nothing
//   node Pipeline\fetch-vod-chat.mjs --for-study          also copy the files to %AppData%\BVQ\chat_logs\import (the bot learns from them
//                                                    at its next study; this costs a few AI calls)
//   node Pipeline/fetch-vod-chat.mjs --history      no chat download: add what each past stream was about (the VOD titles, by Central date) to the bot's
//                                                    stream history (%AppData%BVQchat_history.json) so it knows what you did on those days. Needs no CLI.
//   options: --channel innocentpenguin_   --out D:\PinguinoSuite\Data\chat_logs   --max 200 (VODs per run)   --cli <path to TwitchDownloaderCLI.exe>
//
// HOW IT WORKS
//  * The VOD list comes from Twitch's official API (Helix /videos). It needs TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET, taken from the environment
//    or from D:\PinguinoSuite\PinguinoSite\.env.
//  * Twitch has NO official chat-history API, and its web comment endpoint now answers "failed integrity check" to scripts. So the chat of each VOD
//    is downloaded with TwitchDownloaderCLI (free, open source): get "TwitchDownloaderCLI" for Windows from
//    https://github.com/lay295/TwitchDownloader/releases and put TwitchDownloaderCLI.exe in D:\PinguinoSuite\Tools\ (or on your PATH, or use --cli).
//    The CLI's JSON is converted to the bot's plain .txt format and the JSON is deleted.
//  * LIMIT: Twitch only keeps VODs for 7 days (no Affiliate/Partner), 14 days (Affiliate) or 60 days (Partner); expired / deleted VODs have no
//    chat. "Since the first stream" therefore means as far back as Twitch still has a VOD. Run this now and then (e.g. weekly) to keep the archive growing.
//  * Files: vod-YYYY-MM-DD-<id>.txt, one line per message, UTC, oldest first:   [2026-10-11 23:59:51] #channel user: message
//    The bot reads every *.txt in the archive folder by itself (and shows the times in Central), and skips lines it already has from other files.
import { readFileSync, writeFileSync, existsSync, mkdirSync, copyFileSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { dataDir } from './lib-paths.mjs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i < 0 ? d : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true); };
const channel = String(arg('channel', 'innocentpenguin_')).toLowerCase();
const outDir = String(arg('out', 'D:\\PinguinoSuite\\Data\\chat_logs'));
const since = arg('since', '');
const listOnly = arg('list', false) === true;
const forStudy = arg('for-study', false) === true;
const maxVods = Number(arg('max', 200)) || 200;
const cliArg = arg('cli', '');
const historyOnly = arg('history', false) === true;

function loadEnv() {
  const env = { ...process.env };
  for (const p of ['D:\\PinguinoSuite\\PinguinoSite\\.env', join(process.cwd(), '.env')]) {
    try { for (const l of readFileSync(p, 'utf8').split(/\r?\n/)) { const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)$/.exec(l); if (m && !env[m[1]]) env[m[1]] = m[2].trim().replace(/^["']|["']$/g, ''); } } catch { /* no file */ }
  }
  return env;
}
const env = loadEnv();

async function helixToken() {
  if (!env.TWITCH_CLIENT_ID || !env.TWITCH_CLIENT_SECRET) throw new Error('TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not found (environment or D:\\PinguinoSuite\\PinguinoSite\\.env).');
  const r = await fetch('https://id.twitch.tv/oauth2/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: env.TWITCH_CLIENT_ID, client_secret: env.TWITCH_CLIENT_SECRET, grant_type: 'client_credentials' }) });
  if (!r.ok) throw new Error('Twitch token request failed: ' + r.status);
  return (await r.json()).access_token;
}
async function helix(path, token) {
  const r = await fetch('https://api.twitch.tv/helix/' + path, { headers: { 'Client-Id': env.TWITCH_CLIENT_ID, Authorization: 'Bearer ' + token } });
  if (!r.ok) throw new Error('Helix ' + path + ' failed: ' + r.status);
  return r.json();
}

async function listVods() {
  const token = await helixToken();
  const u = (await helix('users?login=' + encodeURIComponent(channel), token)).data?.[0];
  if (!u) throw new Error('No Twitch user ' + channel);
  const vods = []; let cursor = '';
  do {
    const d = await helix('videos?user_id=' + u.id + '&type=archive&first=100' + (cursor ? '&after=' + cursor : ''), token);
    for (const v of d.data || []) vods.push({ id: v.id, at: v.created_at, title: v.title, duration: v.duration });
    cursor = d.pagination?.cursor || '';
  } while (cursor && vods.length < maxVods);
  return vods.filter(v => !since || v.at.slice(0, 10) >= since).slice(0, maxVods);
}

// TwitchDownloaderCLI: chatdownload --id <vod> -o <file.json>; its JSON has comments[] {created_at, commenter{name, display_name}, message{body}}.
function findCli() {
  const cands = [cliArg && String(cliArg), 'D:\\PinguinoSuite\\Tools\\TwitchDownloaderCLI.exe', 'TwitchDownloaderCLI.exe', 'TwitchDownloaderCLI'].filter(Boolean);
  for (const c of cands) { const r = spawnSync(c, ['--help'], { encoding: 'utf8' }); if (!r.error) return c; }
  return null;
}
const cli = findCli();
function cliChat(id) {
  const tmp = join(tmpdir(), 'vodchat-' + id + '.json');
  const r = spawnSync(cli, ['chatdownload', '--id', id, '-o', tmp, '--collision', 'Overwrite'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0 || !existsSync(tmp)) throw new Error('TwitchDownloaderCLI failed: ' + String(r.stderr || r.stdout || '').split(/\r?\n/).filter(Boolean).slice(-1)[0]);
  const j = JSON.parse(readFileSync(tmp, 'utf8'));
  try { unlinkSync(tmp); } catch { /* ignore */ }
  const rows = [];
  for (const c of j.comments || []) {
    const u = String(c.commenter?.name || c.commenter?.display_name || '').toLowerCase();
    const m = String(c.message?.body || '').replace(/[\r\n]+/g, ' ').trim();
    if (u && m) rows.push({ t: Date.parse(c.created_at), u, m });
  }
  return rows.sort((a, b) => a.t - b.t);
}

const pad = n => String(n).padStart(2, '0');
const stamp = t => { const d = new Date(t); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`; };

(async () => {
  mkdirSync(outDir, { recursive: true });
  const vods = await listVods();
  console.log(`${vods.length} VOD(s) found for ${channel}${since ? ' since ' + since : ''}.` + (vods.length ? ` Oldest: ${vods[vods.length - 1].at.slice(0, 10)}, newest: ${vods[0].at.slice(0, 10)}.` : ' Twitch may have deleted the older ones (7 / 14 / 60 days).'));
  if (historyOnly) {
    const f = join(dataDir(), 'chat_history.json');
    let h = {}; try { h = JSON.parse(readFileSync(f, 'utf8')); } catch { /* new file */ }
    let added = 0;
    for (const v of vods) {
      const ct = new Date(Date.parse(v.at) - 5 * 3600e3);   // Central (daylight time); the stream start is 5 PM CT
      const day = ct.toISOString().slice(0, 10), item = 'stream title: ' + v.title + ' (' + v.duration + ')';
      const l = h[day] || (h[day] = []);
      if (!l.some(x => x.includes(v.title))) { l.push(item); added++; }
    }
    mkdirSync(dataDir(), { recursive: true });
    writeFileSync(f, JSON.stringify(h, null, 1));
    console.log('Added ' + added + ' stream title(s) to ' + f + '. Restart Streamer.bot (or recompile) so the bot reloads it.');
    return;
  }
  if (listOnly) { for (const v of vods) console.log(`  ${v.at.slice(0, 10)}  ${v.id}  ${v.duration}  ${v.title}`); return; }
  if (!cli) {
    console.log('\nTwitchDownloaderCLI was not found, so the chat cannot be downloaded yet (Twitch blocks plain scripts from reading VOD chat).');
    console.log('1) Download "TwitchDownloaderCLI" for Windows from https://github.com/lay295/TwitchDownloader/releases');
    console.log('2) Put TwitchDownloaderCLI.exe in D:\\PinguinoSuite\\Tools\\  (or on your PATH, or run with --cli <full path>)');
    console.log('3) Run this command again.');
    process.exit(2);
  }
  console.log('Using ' + cli + ' for the chat download.');
  const importDir = join(dataDir(), 'chat_logs', 'import');
  let saved = 0, skipped = 0, lines = 0;
  for (const v of vods) {
    const file = join(outDir, `vod-${v.at.slice(0, 10)}-${v.id}.txt`);
    if (existsSync(file)) { skipped++; continue; }
    try {
      const rows = cliChat(v.id);
      if (!rows.length) { console.log(`  ${v.at.slice(0, 10)} ${v.id}: no chat found (VOD chat may be off or expired)`); continue; }
      writeFileSync(file, rows.map(r => `[${stamp(r.t)}] #${channel} ${r.u}: ${r.m}`).join('\n') + '\n', 'utf8');
      saved++; lines += rows.length;
      console.log(`  ${v.at.slice(0, 10)} ${v.id}: ${rows.length} messages -> ${file}`);
      if (forStudy && process.env.APPDATA) { mkdirSync(importDir, { recursive: true }); copyFileSync(file, join(importDir, `vod-${v.id}.txt`)); }
    } catch (e) { console.log(`  ${v.at.slice(0, 10)} ${v.id}: FAILED (${e.message})`); }
  }
  console.log(`Done: ${saved} new VOD chat file(s), ${lines} messages, ${skipped} already downloaded. The bot searches them automatically.`);
})().catch(e => { console.error('ERROR: ' + e.message); process.exit(1); });
