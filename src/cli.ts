#!/usr/bin/env node
import {readFileSync} from 'node:fs';
import {ALGORITHM_VERSION,DIFFICULTIES,scoreMaidata,type Difficulty} from './index';

const HELP=`DXTag ${ALGORITHM_VERSION} · 五维评分 0.0–10.0

用法：dxtag-score <maidata.txt> [-d 3,5,8 | --all] [--json]

默认计算全部正文非空的 inote_N 槽位，按编号升序输出。
-d, --difficulty  正安全整数或 easy / basic / advanced / expert / master / remaster / re:master / utage
                  多项用逗号分隔，也可重复使用 -d
--all             计算全部槽位；与 -d 互斥
--json            JSON 输出（默认）；分数固定显示一位小数
-h, --help        显示帮助

输出数组，每项包含 title、slot、difficulty、scores。
退出码：0 成功；1 存在解析/计算失败；2 参数、文件读取、编码或槽位选择错误。
`;
function parseDifficulty(value: string): Difficulty {
  const normalized = value.trim().toLowerCase();
  const named = Object.entries(DIFFICULTIES).find(([,name])=>
    name.toLowerCase()===normalized || name.toLowerCase().replace(':','')===normalized);
  if (named) return Number(named[0]);
  const slot = Number(normalized);
  if (!/^[1-9]\d*$/.test(normalized) || !Number.isSafeInteger(slot)) {
    throw new Error(`难度参数“${value}”无效；有效值为正安全整数或难度名称。`);
  }
  return slot;
}
function main(args:string[]) {
  if (args.includes('--help')||args.includes('-h')) {process.stdout.write(HELP);return;}
  let file:string|undefined,all=false;
  const difficulties:Difficulty[]=[];
  for (let i=0;i<args.length;i++) {
    const arg=args[i]!;
    if(arg==='--json')continue;
    if(arg==='--all'){all=true;continue;}
    if(arg==='-d'||arg==='--difficulty'){
      const value=args[++i];
      if(value===undefined)throw new Error('-d 缺少难度参数。');
      difficulties.push(...value.split(',').map(parseDifficulty));continue;
    }
    if(arg.startsWith('-'))throw new Error(`未知参数：${arg}`);
    if(file)throw new Error('maidata 文件路径数量须为 1。');
    file=arg;
  }
  if(!file)throw new Error('缺少 maidata 文件路径。');
  if(all&&difficulties.length)throw new Error('--all 与 -d 互斥。');
  const bytes=readFileSync(file);
  const encoding=bytes[0]===0xff&&bytes[1]===0xfe?'utf-16le':bytes[0]===0xfe&&bytes[1]===0xff?'utf-16be':'utf-8';
  let text:string;
  try{text=new TextDecoder(encoding,{fatal:true}).decode(bytes);}catch{throw new Error('文件编码无效；支持 UTF-8 及带 BOM 的 UTF-16 LE／BE。');}
  const result=scoreMaidata(text,difficulties.length?difficulties:'all',error=>{
    process.stderr.write(`inote_${error.slot}（${error.difficulty}）：${error.message}\n`);
    process.exitCode=1;
  });
  const serialized=JSON.stringify(result,null,2).replace(/("(?:键盘|星星|技巧|体力|爆发)": )([\d.]+)/g,(_match,prefix,value)=>prefix+Number(value).toFixed(1));
  process.stdout.write(serialized+'\n');
}
try{main(process.argv.slice(2));}catch(error){process.stderr.write(`错误：${error instanceof Error?error.message:String(error)}\n`);process.exitCode=2;}
