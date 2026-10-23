// The guessed OBS names (BRB, Main, Mic/Aux) live in one map (cfg.obsNames). Run: node src/namescheck.mjs
import './testenv.mjs';
import { startFakeObs } from './fakeobs.mjs';
import { GUESSES, names, resolveName, resolveSteps, nameHint } from './names.mjs';
import { runMacro } from './server.mjs';
import { prestream } from './prestream.mjs';
import * as macros from './macros.mjs';
import { DEFAULTS } from './config.mjs';

let bad = 0;
const check = (n, c, x = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + x}`); if (!c) bad++; };

// --- the map itself
check('defaults are the old guesses', JSON.stringify(names({})) === JSON.stringify({ brb: 'BRB', main: 'Main', mic: 'Mic/Aux' }) && JSON.stringify(DEFAULTS.obsNames) === JSON.stringify(GUESSES));
check('one key overrides one name', names({ obsNames: { main: 'Gameplay' } }).main === 'Gameplay' && names({ obsNames: { main: 'Gameplay' } }).brb === 'BRB');
check('blank, non-string and prototype keys are ignored', JSON.stringify(names({ obsNames: { main: '  ', brb: 5, mic: null, constructor: 'x', __proto__: 'y' } })) === JSON.stringify(GUESSES));
check('names() survives a non-object map', JSON.stringify(names({ obsNames: 'oops' })) === JSON.stringify(GUESSES) && JSON.stringify(names(null)) === JSON.stringify(GUESSES));
check('only the guessed text is translated', resolveName({ obsNames: { main: 'Gameplay' } }, 'Main') === 'Gameplay' && resolveName({ obsNames: { main: 'Gameplay' } }, 'Other') === 'Other' && resolveName({}, 'Mic/Aux') === 'Mic/Aux');
const cfgA = { obsNames: { main: 'Gameplay', mic: 'Shure MV7' } };
const steps = [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }, { type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }, { type: 'StopStream' }];
const rs = resolveSteps(cfgA, steps);
check('resolveSteps translates scenes and inputs and leaves the config alone', rs[0].data.sceneName === 'Gameplay' && rs[1].data.inputName === 'Shure MV7' && rs[2].type === 'StopStream' && steps[0].data.sceneName === 'Main');
check('the hint names the config key for a guess and not for a custom name', /"obsNames": \{ "main"/.test(nameHint('Main')) && !/obsNames/.test(nameHint('Starting Soon')));

// --- against a fake OBS whose real scene is called "Gameplay"
const f = await startFakeObs('pw-secret-1');
f.obs.scenes = ['Gameplay', 'Starting']; f.obs.scene = 'Starting'; f.obs.inputs = ['Shure MV7'];
const mk = obsNames => ({ role: 'hub', hub: 'x', port: 1, token: 't', obs: { host: '127.0.0.1', port: f.obsPort, password: 'pw-secret-1' }, ...(obsNames ? { obsNames } : {}),
  macros: { live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }], brb: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }], mute: [{ type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }], custom: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Nope' } }] },
  claude: { enabled: false }, prestream: { tailscale: false, disk: false } });
try {
  let err = null; try { await runMacro(mk(), 'live'); } catch (e) { err = e; }
  check('missing scene error names the scene and the one-line fix', !!err && /OBS has no scene named "Main"/.test(err.message) && /"obsNames": \{ "main": "<the real OBS name>" \}/.test(err.message), err?.message);
  err = null; try { await runMacro(mk(), 'custom'); } catch (e) { err = e; }
  check('a custom scene name gets the "edit the macro" hint', !!err && /OBS has no scene named "Nope"/.test(err.message) && /Edit the macro/.test(err.message) && !/obsNames/.test(err.message), err?.message);
  err = null; try { await runMacro(mk(), 'mute'); } catch (e) { err = e; }
  check('missing input error names the input', !!err && /OBS has no input named "Mic\/Aux"/.test(err.message) && /"mic"/.test(err.message), err?.message);
  await runMacro(mk({ main: 'Gameplay' }), 'live');
  check('after the one-line change the macro works', f.obs.scene === 'Gameplay');
  const before = f.obs.muted; await runMacro(mk({ mic: 'Shure MV7' }), 'mute');
  check('input name map works too', f.obs.muted === !before);

  // missing() (macro editor) and the pre-stream report
  check('macros.missing uses the map', macros.missing(mk(), 'live', { scenes: f.obs.scenes, inputs: f.obs.inputs }).length === 1 && macros.missing(mk({ main: 'Gameplay' }), 'live', { scenes: f.obs.scenes, inputs: f.obs.inputs }).length === 0);
  const pre = (await prestream(mk())).find(i => i.id === 'macros');
  check('pre-stream names every missing scene/input with its fix', pre?.status === 'fail' && /live: scene "Main"/.test(pre.detail) && /brb: scene "BRB"/.test(pre.detail) && /mute: input "Mic\/Aux"/.test(pre.detail) && /obsNames/.test(pre.detail), pre?.detail);
  const ok = (await prestream(mk({ main: 'Gameplay', brb: 'Starting', mic: 'Shure MV7' }))).find(i => i.id === 'macros');
  check('pre-stream: with the map set only the truly wrong one is left', ok?.status === 'fail' && /custom: scene "Nope"/.test(ok.detail) && !/live:|brb:|mute:/.test(ok.detail), ok?.detail);
  check('nothing went live', f.obs.streaming === false && !f.obs.log.some(t => /Stream/.test(t) && t !== 'GetStreamStatus'));
} finally { f.close(); }
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll OBS-name checks passed');
process.exit(bad ? 1 : 0);
