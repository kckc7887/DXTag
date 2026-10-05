#!/usr/bin/env node
import {readFileSync} from 'node:fs';
import {DIFFICULTIES,scoreMaidata,type Difficulty} from './index';

const HELP=`DXTag 五维评分 0.0–10.0

用法：node dist/cli.mjs <maidata.txt> [--difficulty master] [--json]
      npm run score -- <maidata.txt> [-d 5] [--json]

默认计算文件中的全部普通谱（inote_2 至 inote_6）。
-d, --difficulty  basic / advanced / expert / master / remaster，或 2–6
--json            JSON 输出（默认）；分数固定显示一位小数
-h, --help        显示帮助

输出数组，每项包含 title、difficulty、scores（全曲库）和 chartRelativeScores（谱面自身）。
同谱五维比较用 chartRelativeScores；跨谱比较用 scores。
谱内分数独立分析原始动作：75% 整谱平均负担 + 25% 高负担分位，最强维度为 10.0。
退出码：0 成功；1 存在解析/计算失败；2 参数、文件读取或普通谱选择错误。
`;
function main(args:string[]) {
  if (args.includes('--help')||args.includes('-h')) {process.stdout.write(HELP);return;}
  let file:string|undefined,difficulty:Difficulty|undefined;
  for (let i=0;i<args.length;i++) {
    const arg=args[i]!;
    if(arg==='--json')continue;
    if(arg==='-d'||arg==='--difficulty'){
      const value=args[++i]?.toLowerCase();
      const selected=Object.entries(DIFFICULTIES).find(([slot,name])=>slot===value||name.toLowerCase().replace(':','')===value?.replace(':',''));
      if(!selected||difficulty!==undefined)throw new Error('请用 -d 指定一个普通谱难度（2–6 或 basic 至 remaster）。');
      difficulty=Number(selected[0]) as Difficulty;continue;
    }
    if(arg.startsWith('-'))throw new Error(`未知参数：${arg}`);
    if(file)throw new Error('一次只输入一个 maidata 文件。');
    file=arg;
  }
  if(!file)throw new Error('缺少 maidata 文件路径。用 --help 查看用法。');
  const bytes=readFileSync(file);
  const encoding=bytes[0]===0xff&&bytes[1]===0xfe?'utf-16le':bytes[0]===0xfe&&bytes[1]===0xff?'utf-16be':'utf-8';
  let text:string;
  try{text=new TextDecoder(encoding,{fatal:true}).decode(bytes);}catch{throw new Error('文件编码无法识别，请保存为 UTF-8（也支持带 BOM 的 UTF-16）。');}
  const result=scoreMaidata(text,difficulty,error=>{
    process.stderr.write(`${error.difficulty}：${error.message}\n`);
    process.exitCode=1;
  });
  const serialized=JSON.stringify(result,null,2).replace(/("(?:键盘|星星|技巧|体力|爆发)": )([\d.]+)/g,(_match,prefix,value)=>prefix+Number(value).toFixed(1));
  process.stdout.write(serialized+'\n');
}
try{main(process.argv.slice(2));}catch(error){process.stderr.write(`错误：${error instanceof Error?error.message:String(error)}\n`);process.exitCode=2;}
