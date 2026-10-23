// Import FIRST in every *check.mjs: tests must never inherit the live Suite's environment (API token, core URL, data dir, ports).
// Without this a check run from a session that has the real PINGUINO_API_TOKEN talks to the live core and fails/warns for the wrong reasons.
for (const k of Object.keys(process.env)) if (/^PINGUINO_/.test(k) && k !== 'PINGUINO_NEVER_REAL_OBS') delete process.env[k];
process.env.PINGUINO_NEVER_REAL_OBS = '1';
