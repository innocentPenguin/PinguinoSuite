// INDEX profiles.mjs: install profiles. A profile is the set of release parts an install keeps; install.json records it as `profile` + `parts`.
//   full          every part (this PC). install.json carries no `parts`, so nothing is filtered.
//   lite-minimal  the PinguinoLite PC: Lite's own files, Link, and the updater/scripts. Other modules are added later on demand (updater `apply --only <part>`).
// Parts that are not installed are never updated, never listed as changes, and never counted against "everything is current"; check lists them as `optional`.
import { COMPONENTS } from './components.mjs';

export const PROFILES = {
  full: { name: 'Full Suite', parts: null },
  'lite-minimal': { name: 'PinguinoLite (minimal)', parts: ['lite', 'link', 'tools'] },
};

/** The parts an install keeps: explicit `parts` in install.json, else its profile, else null (= all). */
export function partsOf(inst) {
  if (inst && Array.isArray(inst.parts)) return inst.parts;
  const p = inst && inst.profile && PROFILES[inst.profile];
  return p ? p.parts : null;
}
export const wants = (parts, id) => !parts || parts.includes(id);

/** Parts that can be added or taken away on demand (modules and Lite's own optional pieces); app parts and scripts are fixed by the profile. */
export const isOptionalPart = id => { const c = COMPONENTS.find(x => x.id === id); return !!c && c.restart === 'module'; };
