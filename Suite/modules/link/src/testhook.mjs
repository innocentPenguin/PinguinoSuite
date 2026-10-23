// INDEX testhook.mjs: test-only environment switches work only in a test run, never in a real Suite run.
import os from 'node:os';

/** True when `name` is exactly "1" AND this is not a real Suite run (a real run has PINGUINO_API_TOKEN set and a data dir outside the temp folder). */
export function testHook(name) {
  if (process.env[name] !== '1') return false;
  const tmp = (process.env.PINGUINO_DATA_DIR || '').toLowerCase().startsWith(os.tmpdir().toLowerCase());
  if (process.env.PINGUINO_API_TOKEN && !tmp) return false;
  return true;
}
