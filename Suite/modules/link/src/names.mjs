// INDEX names.mjs: the OBS scene/input names Link had to guess (BRB, Main, Mic/Aux) live in ONE map, cfg.obsNames
// ({ brb, main, mic }). Macros keep the guessed text; it is translated to the real OBS name when a macro runs or is checked.
// To match Ivan's real OBS: change one line in the Link config, e.g.  "obsNames": { "main": "Gameplay" }.
export const GUESSES = Object.freeze({ brb: 'BRB', main: 'Main', mic: 'Mic/Aux' });
const KEY_OF = new Map(Object.entries(GUESSES).map(([k, v]) => [v, k]));   // guessed text -> key

const clean = v => (typeof v === 'string' && v.trim() && v.length <= 200 ? v.trim() : '');
/** The effective map: guesses overridden by whatever the config sets. */
export function names(cfg) {
  const o = cfg?.obsNames && typeof cfg.obsNames === 'object' ? cfg.obsNames : {};
  return Object.fromEntries(Object.entries(GUESSES).map(([k, d]) => [k, Object.hasOwn(o, k) && clean(o[k]) || d]));
}
/** Guessed text -> real OBS name (anything else is returned as it is). */
export function resolveName(cfg, text) {
  const k = typeof text === 'string' && KEY_OF.get(text);
  return k ? names(cfg)[k] : text;
}
/** OBS requests with guessed scene/input names replaced by the configured ones (new objects; the config is not changed). */
export function resolveSteps(cfg, steps) {
  return steps.map(s => {
    if (!s || !s.data || (s.data.sceneName === undefined && s.data.inputName === undefined)) return s;
    const data = { ...s.data };
    if (data.sceneName !== undefined) data.sceneName = resolveName(cfg, data.sceneName);
    if (data.inputName !== undefined) data.inputName = resolveName(cfg, data.inputName);
    return { ...s, data };
  });
}
/** One line telling what to change when OBS does not have the name. */
export function nameHint(text) {
  const k = typeof text === 'string' && KEY_OF.get(text);
  return k ? `"${text}" is a guess. Set "obsNames": { "${k}": "<the real OBS name>" } in the Link config, or edit the macro.`
    : 'Edit the macro and pick a name that exists in OBS.';
}
/** "scene "X"" / "input "X"" for a request, or '' */
export function targetOf(req) {
  if (req?.data?.sceneName) return { kind: 'scene', name: req.data.sceneName };
  if (req?.data?.inputName) return { kind: 'input', name: req.data.inputName };
  return null;
}
