"""Small exact-arithmetic checker restricted to the uploaded MASTER chart syntax.
Does NOT import the demo parser/detector. Rejects syntax outside this fixture.
"""
from fractions import Fraction as F
from pathlib import Path
import re, json
text=(Path(__file__).parent / 'regression' / 'umiyuri_user_maidata.txt').read_text(encoding='utf-8-sig')
body=text.split('&inote_5=',1)[1].split('&inote_',1)[0]
t,bpm,divider=F(0),F(120),F(4)
attacks=[]; slides=[]
for raw in body.split(','):
    cell=''.join(raw.split())
    while cell.startswith(('(', '{')):
        closer=')' if cell[0]=='(' else '}'
        k=cell.index(closer); val=F(cell[1:k])
        if cell[0]=='(':bpm=val
        else:divider=val
        cell=cell[k+1:]
    if cell=='E':break
    for token in cell.split('/'):
        if not token:continue
        assert re.fullmatch(r'[1-8](?:b|h\[\d+:\d+\]|(?:[-^<>pqsz][1-8])\[\d+:\d+\])?',token),token
        p=int(token[0]); attacks.append((t,p, 'hold' if 'h' in token else 'tap'))
        if re.match(r'[1-8][-^<>pqsz]',token):
            x,y=map(int,re.search(r'\[(\d+):(\d+)\]',token).groups())
            slides.append((t,t+60/bpm,t+60/bpm+240*F(y,x)/bpm,p))
    t+=240/bpm/divider
foreign=same=hai=0
records=[]
for head,start,end,pos in slides:
    waitnotes=[(tt,p,k) for tt,p,k in attacks if head<tt<start]
    launch=[(p,k) for tt,p,k in attacks if tt==start]
    headkeys={p for tt,p,k in attacks if tt==head}
    fw=any(p!=pos for _,p,_ in waitnotes)
    sl=any(p==pos and k=='tap' for p,k in launch)
    midpoint=any(tt==(head+start)/2 and p!=pos for tt,p,k in attacks)
    shape=fw and sl and midpoint and len(headkeys)>=2 and len({p for p,k in launch})>=2
    foreign+=fw;same+=sl;hai+=shape
    records.append({'head':float(head),'start':float(start),'end':float(end),'origin':pos,'foreign_wait':fw,'same_origin_launch':sl,'umiyuri_structure':shape})
report={'method':'independent raw-string parser with fractions.Fraction; exact timestamps; no demo imports', 'judged_objects':len(attacks)+len(slides),'slide_count':len(slides),'foreign_wait':foreign,'same_origin_launch':same,'umiyuri_structure':hai,'records':records}
(Path(__file__).parent / 'regression' / 'reference_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print({k:v for k,v in report.items() if k!='records'})
assert (len(attacks)+len(slides),len(slides),foreign,same,hai)==(759,76,53,46,46)
