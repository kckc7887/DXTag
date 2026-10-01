import {build} from 'esbuild';
await build({entryPoints:{cli:'src/cli.ts',index:'src/index.ts'},outdir:'dist',outExtension:{'.js':'.mjs'},
  bundle:true,platform:'node',format:'esm',target:'node22',legalComments:'eof',logLevel:'info',
  banner:{js:'/*! DXTag | MIT License | Copyright (c) 2026 尘言 | See LICENSE */'}});
