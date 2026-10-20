import {build} from 'esbuild';
import {readFileSync} from 'node:fs';
const {version} = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
await build({entryPoints:{cli:'src/cli.ts',index:'src/index.ts'},outdir:'dist',outExtension:{'.js':'.mjs'},
  bundle:true,platform:'node',format:'esm',target:'node22',legalComments:'eof',logLevel:'info',
  define:{__DXTAG_VERSION__:JSON.stringify(version)},
  banner:{js:'/*! DXTag | MIT License | Copyright (c) 2026 尘言 | See LICENSE */'}});
