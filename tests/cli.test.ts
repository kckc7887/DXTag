import assert from 'node:assert/strict';
import {after, test} from 'node:test';
import {copyFileSync, mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const temporaryRoot = resolve(tmpdir());
const temporary = mkdtempSync(join(temporaryRoot, 'dxtag-five-axis-test-'));
// Exercise the bundled CLI from a directory containing neither project data
// nor node_modules. Its only inputs are this file and the embedded scale.
const cli = join(temporary, '独立评分.mjs');
copyFileSync(fileURLToPath(new URL('../dist/cli.mjs', import.meta.url)), cli);
const source = '&title=中文曲名\n&inote_4=(120){8}1,2,3,4,5,6,7,8,E\n&inote_5=(120){4}1-5[4:2],2,3,4,E';
const file = join(temporary, '含 空格 maidata.txt');
writeFileSync(file, source);
const run = (...args: string[]) => spawnSync(process.execPath, [cli, ...args], {cwd:temporary, encoding:'utf8'});

after(() => {
  const target = resolve(temporary);
  assert.equal(dirname(target), temporaryRoot);
  assert.ok(basename(target).startsWith('dxtag-five-axis-test-'));
  rmSync(target, {recursive:true});
});

test('standalone bundle accepts Unicode paths and emits numeric one-decimal JSON', () => {
  const result = run(file, '--json');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, '');
  const parsed = JSON.parse(result.stdout);
  assert.ok(Array.isArray(parsed));
  assert.deepEqual(parsed.map((chart: {difficulty:string}) => chart.difficulty), ['EXPERT','MASTER']);
  for(const chart of parsed){
    assert.deepEqual(Object.keys(chart), ['title','difficulty','scores']);
    assert.equal(chart.title, '中文曲名');
  }
  assert.match(result.stdout, /"星星": 0\.0/);
  const decimals = [...result.stdout.matchAll(/"(?:键盘|星星|技巧|体力|爆发)": (\d+\.\d)(?=,|\s)/g)];
  assert.equal(decimals.length, 10);
  assert.equal(typeof parsed[0].scores.键盘, 'number');
  assert.equal(run(file).stdout, result.stdout);
});

test('difficulty aliases and numeric slots agree; single-chart output remains an array', () => {
  const named = run(file, '--difficulty', 'MASTER', '--json');
  const numbered = run(file, '-d', '5', '--json');
  assert.equal(named.status, 0, named.stderr);
  assert.equal(named.stdout, numbered.stdout);
  assert.equal(JSON.parse(named.stdout).length, 1);
  assert.equal(run(file, '-d', '5').stdout, named.stdout);
});

test('UTF-8 BOM and UTF-16 BOM files yield the same scores', () => {
  const plain = run(file, '--json').stdout;
  const le = Buffer.from(source, 'utf16le');
  const be = Buffer.from(le).swap16();
  for (const [name, bytes] of [
    ['utf8', Buffer.concat([Buffer.from([0xef,0xbb,0xbf]), Buffer.from(source)])],
    ['utf16le', Buffer.concat([Buffer.from([0xff,0xfe]), le])],
    ['utf16be', Buffer.concat([Buffer.from([0xfe,0xff]), be])],
  ] as const) {
    const path = join(temporary, name + '.txt');
    writeFileSync(path, bytes);
    const result = run(path, '--json');
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, plain);
  }
});

test('partial chart failures use exit code 1 and preserve successes in JSON', () => {
  const path = join(temporary, 'partial.txt');
  writeFileSync(path, source + '\n&inote_6=(120){0}1,E');
  const result = run(path, '--json');
  assert.equal(result.status, 1);
  const parsed = JSON.parse(result.stdout);
  assert.equal(parsed.length, 2);
  assert.ok(parsed.every((chart: object)=>Object.keys(chart).join(',')==='title,difficulty,scores'));
  assert.match(result.stderr, /Re:MASTER/);
});

test('all failed charts emit an empty array and diagnostics on stderr', () => {
  const path = join(temporary, 'failed.txt');
  writeFileSync(path, '&title=坏谱\n&inote_5=(120){0}1,E');
  const result = run(path);
  assert.equal(result.status, 1);
  assert.deepEqual(JSON.parse(result.stdout), []);
  assert.match(result.stderr, /MASTER/);
});

test('title comes from maidata and JSON preserves embedded quotes and escapes', () => {
  const path=join(temporary, 'title.txt');
  const title='曲名 "键盘": 1 / \\path';
  writeFileSync(path, source.replace('中文曲名',title));
  const result=run(path,'-d','5');
  assert.equal(result.status,0,result.stderr);
  assert.equal(JSON.parse(result.stdout)[0].title,title);
});

test('argument, missing file and undecodable input errors use exit code 2', () => {
  const invalid = join(temporary, 'bad-encoding.txt');
  writeFileSync(invalid, Buffer.from([0x80,0x80]));
  for (const args of [[], [file,'--unknown'], [file,'-d','1'], [file,'-d','5','-d','4'],
    [file,file], [join(temporary,'missing.txt')], [invalid]]) {
    const result = run(...args);
    assert.equal(result.status, 2, args.join(' '));
    assert.match(result.stderr, /错误/);
  }
  assert.match(run(invalid).stderr, /编码/);
  assert.equal(run('--help').status, 0);
});
