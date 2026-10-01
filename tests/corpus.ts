import {existsSync} from 'node:fs';
import {resolve} from 'node:path';

export function corpusFile(relative: string): string | undefined {
  const root = process.env.DXTAG_CHARTS_DIR;
  if (!root) return undefined;
  const file = resolve(root, relative, 'maidata.txt');
  return existsSync(file) ? file : undefined;
}
