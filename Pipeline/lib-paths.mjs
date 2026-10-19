// One place that decides where the bot data lives (shared by every Pipeline script).
// Order: PINGUINO_DATA_DIR -> BVQ_DATA_DIR (deprecated alias) -> legacy %AppData%\BVQ while it exists (what the live bots still read,
// so the pipeline and the bots never split) -> <Suite>\Data\runtime. Cutover = set PINGUINO_DATA_DIR for the bots AND the pipeline task.
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export function dataDir() {
  const env = process.env.PINGUINO_DATA_DIR || process.env.BVQ_DATA_DIR;
  if (env) return env;
  const legacy = join(process.env.APPDATA || '', 'BVQ');
  if (existsSync(legacy)) return legacy;
  return join(dirname(fileURLToPath(import.meta.url)), '..', 'Data', 'runtime');
}
