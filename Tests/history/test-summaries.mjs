// Tests for Pipeline\build-summaries.mjs with the fake AI (no API, no cost) on a tiny made-up log in a temp folder.
//   node Tests\history\test-summaries.mjs
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const script = 'D:\\PinguinoSuite\\Pipeline\\build-summaries.mjs';
const root = mkdtempSync(join(tmpdir(), 'hist-'));
const logs = join(root, 'logs'), out = join(root, 'out'), app = join(root, 'app');
mkdirSync(join(logs, '2026', '09'), { recursive: true }); mkdirSync(join(logs, '2026', '10'), { recursive: true }); mkdirSync(app, { recursive: true });

let pass = 0, fail = 0;
const check = (name, ok, extra = '') => { if (ok) pass++; else { fail++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } };

// stream days (Central): 2026-09-30 (starts 22:00 UTC), 2026-10-01, 2026-10-02; the last one runs past midnight Central
function day(file, utcDate, users) {
  const lines = [];
  for (let i = 0; i < 40; i++) {
    const u = users[i % users.length];
    const hh = String(22 + Math.floor(i / 20)).padStart(2, '0'), mm = String((i * 3) % 60).padStart(2, '0');
    lines.push(`[${utcDate} ${hh}:${mm}:10] #innocentpenguin_ ${u}: message number ${i} about rocket league and cats with enough words to count`);
  }
  lines.push(`[${utcDate} 22:04:00] #innocentpenguin_ bravo: hey @ghosty that was a really nice play yesterday`);
  lines.push(`[${utcDate} 22:05:00] #innocentpenguin_ nightbot: bot line that must be ignored`);
  lines.push(`[${utcDate} 22:06:00] #innocentpenguin_ alpha: !join`);
  lines.push(`[${utcDate} 22:07:00] #innocentpenguin_ alpha: i want to die today and this must be skipped`);
  lines.push(`[${utcDate} 22:08:00] #innocentpenguin_ * 5 raiders from SomeStreamer have joined!`);
  writeFileSync(join(logs, '2026', file.slice(0, 2), '2026-' + file.slice(0, 2) + '-' + file.slice(3) + '.txt'), lines.join('\n') + '\n');
}
day('09-30', '2026-09-30', ['alpha', 'bravo', 'ghosty']);
day('10-01', '2026-10-01', ['alpha', 'bravo', 'ghosty']);
day('10-02', '2026-10-02', ['alpha', 'bravo']);
// privacy: ghosty asked to be forgotten
writeFileSync(join(app, 'chat_memory.json'), JSON.stringify({ id_ghosty: { Id: 'id_ghosty', Login: 'ghosty', Privacy: 'anon', Display: 'Ghosty', Aliases: [] } }));
writeFileSync(join(app, 'chat_settings.json'), JSON.stringify({ Provider: 'claude', ApiKey: 'x' }));

const run = extra => spawnSync('node', [script, '--fake', '--logs', logs, '--out', out, '--appdata', app, '--min-msgs', '10', ...extra], { encoding: 'utf8', env: { ...process.env, PINGUINO_DUMP: join(root, 'prompts.txt') } });

// dry run: nothing is created, a plan is printed
let r = run(['--dry-run']);
check('dry run prints a plan', /Would do: 3 daily/.test(r.stdout), r.stdout + r.stderr);
check('dry run writes nothing', !existsSync(out));

// real (fake-AI) run
r = run([]);
check('run finishes', /Done\./.test(r.stdout), r.stdout + r.stderr);
const daily = readdirSync(join(out, 'daily'));
check('one daily file per stream day', daily.length === 3 && daily.includes('2026-09-30.json') && daily.includes('2026-10-02.json'), daily.join(','));
const d1 = JSON.parse(readFileSync(join(out, 'daily', '2026-10-01.json'), 'utf8'));
check('daily has the fields', d1.summary && d1.games.length && d1.topics.length && d1.moments.length && d1.messages === 42, JSON.stringify(d1).slice(0, 200));
check('contact details in an AI answer are filtered out', !/example\.com/.test(d1.summary), d1.summary);
const dump = readFileSync(join(root, 'prompts.txt'), 'utf8');
check('bot lines and !commands never reach the AI', !/nightbot|bot line that must|!join/i.test(dump));
check('heavy talk never reaches the AI', !/want to die/i.test(dump));
check('a forgotten viewer is never named to the AI', !/ghosty/i.test(dump) && /someone/.test(dump));
check('weekly summaries exist', existsSync(join(out, 'weekly')) && readdirSync(join(out, 'weekly')).length >= 1, existsSync(join(out, 'weekly')) ? readdirSync(join(out, 'weekly')).join(',') : 'none');
const w = JSON.parse(readFileSync(join(out, 'weekly', readdirSync(join(out, 'weekly'))[0]), 'utf8'));
check('weekly lists its days', Array.isArray(w.days) && w.days.length >= 1);

// monthly highlights
check('monthly file for an active viewer', existsSync(join(out, 'monthly', 'alpha', '2026-10.json')));
const mo = JSON.parse(readFileSync(join(out, 'monthly', 'alpha', '2026-10.json'), 'utf8'));
check('interests kept', mo.interests.includes('Likes the Cowboys') && mo.interests.includes('Plays Rocket League'), JSON.stringify(mo));
check('an age in an AI answer is filtered out', !mo.interests.some(x => /15 years/.test(x)), JSON.stringify(mo.interests));
check('a viewer who asked to be forgotten gets NO monthly file', !existsSync(join(out, 'monthly', 'ghosty')));
check('and is called someone in the daily results', !/ghosty/i.test(JSON.stringify(d1)), JSON.stringify(d1).slice(0, 300));
check('index written', existsSync(join(out, 'INDEX.md')) && JSON.parse(readFileSync(join(out, 'index.json'), 'utf8')).daily.length === 3);

// incremental: a second run makes no AI calls
r = run([]);
check('second run does nothing new', /0 AI call/.test(r.stdout), r.stdout);

// --limit
mkdirSync(join(root, 'out2'), { recursive: true });
r = spawnSync('node', [script, '--fake', '--logs', logs, '--out', join(root, 'out2'), '--appdata', app, '--limit', '2'], { encoding: 'utf8' });
check('--limit stops at the call limit', /Stopped at the call limit/.test(r.stdout) && /2 AI call/.test(r.stdout), r.stdout);

// --force redoes
r = run(['--force', '--daily']);
check('--force redoes the dailies', /3 AI call/.test(r.stdout) || /Daily: 3 to do/.test(r.stdout), r.stdout);

console.log(fail === 0 ? `ALL ${pass} HISTORY CHECKS PASSED` : `${fail} FAILED / ${pass} passed`);
process.exit(fail === 0 ? 0 : 1);
