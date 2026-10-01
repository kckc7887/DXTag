import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {scoreChart, AXES, type Difficulty} from '../src/index';
import {corpusFile} from './corpus';

// Fixed scores for optional real-chart regression.
const cases: [string, Difficulty, number[]][] = [
  ['27. CiRCLE PLUS/TECHNOPOLIS 2085',5,[8.5,5.1,8.9,4.2,5.6]],
  ['19. UNiVERSE PLUS/enchanted love',5,[7,6.8,8.2,4.7,5.6]],
  ['03. GreeN/神室雪月花',4,[1.3,3.4,4.6,1.3,3.6]],
  ['11. MiLK/Kinda Way',4,[2.9,4.5,5.6,3,3.4]],
  ['18. UNiVERSE/インドア系ならトラックメイカー',5,[6.7,6.3,7.7,10,7.9]],
  ['12. MiLK PLUS/花と、雪と、ドラムンベース。',6,[2.8,7.6,7.6,5.4,3.8]],
  ['25. PRiSM PLUS/Amereistr',5,[7.1,5.7,8.6,5,5.5]],
  ['01. maimai/True Love Song',5,[4.8,2.1,6.8,5,3.7]],
  ['18. UNiVERSE/Upshift',5,[7.1,8,9,6.6,7.9]],
  ['13. FiNALE/PANDORA PARADOXXX',5,[10,9.7,9.6,10,9.7]],
  ['13. FiNALE/PANDORA PARADOXXX',6,[10,8.3,9.9,10,9.5]],
  ['25. PRiSM PLUS/Xaleid◆scopiX',5,[10,10,9.9,8.2,9.8]],
];
for(const [relative,slot,expected]of cases){
  const file=corpusFile(relative);
  test(`frozen five scores: ${relative} inote_${slot}`,{skip:!file},()=>{
    const result=scoreChart(fs.readFileSync(file!,'utf8'),slot);
    assert.deepEqual(AXES.map(axis=>result.scores[axis]),expected);
  });
}
