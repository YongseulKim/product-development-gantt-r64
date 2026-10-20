"""Syntax, static IDs and isolated date calculations; does not simulate a browser."""
from pathlib import Path
from html.parser import HTMLParser
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.blocks=[];self.block=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='script':self.block=[attrs,'']
    def handle_data(self,data):
        if self.block is not None:self.block[1]+=data
    def handle_endtag(self,tag):
        if tag=='script' and self.block is not None:self.blocks.append(self.block);self.block=None
p=Parser();p.feed((ROOT/'index.html').read_text())
assert len(p.ids)==len(set(p.ids)), 'Duplicate IDs'
scripts=[s for attrs,s in p.blocks if attrs.get('type')!='application/json']
for script in scripts:
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)/'script.js';p.write_text(script,encoding='utf-8');subprocess.run(['node','--check',str(p)],check=True)
s='\n'.join(scripts)
functions=s[s.index('function iso(date)'):s.index('function actual(n)')]
checks=r'''
const assert=require('node:assert/strict');let count=0;
function check(actual,expected){assert.deepEqual(actual,expected);count++;}
check(validDate('2028-02-29'),true);check(validDate('2026-02-29'),false);
check(validDate('2026-13-01'),false);check(validDate('2026-1-01'),false);
kickoffDate='2026-10-23';check(dateAt(BASE),'2026-10-23');check(dateAt(BASE+1),'2026-10-26');check(dateAt(BASE-1),'2026-10-22');
refreshHolidays('2026-10-26');check(dateAt(BASE+1),'2026-10-27');
refreshHolidays('');BUILTIN_HOLIDAYS.add('2026-10-26');check(dateAt(BASE+1),'2026-10-27');
refreshHolidays('-2026-10-26');check(dateAt(BASE+1),'2026-10-26');
check(completionAt(BASE+1),'2026-10-23');
BUILTIN_HOLIDAYS.clear();refreshHolidays('');kickoffDate='2026-10-24';check(dateAt(BASE),'2026-10-26');
kickoffDate='2028-02-28';check(dateAt(BASE+1),'2028-02-29');check(dateAt(BASE+2),'2028-03-01');
kickoffDate='2026-12-31';check(dateAt(BASE+1),'2027-01-01');
assert.throws(()=>parseHolidays('2026-02-30'));count++;
check(dateAt(BASE+731),'');check(dateAt(BASE+0.5),'');
console.log(JSON.stringify({dateChecks:count,passed:true}));
'''
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)/'dates.js';p.write_text('const BASE=0,addedHolidays=new Set(),removedHolidays=new Set(),BUILTIN_HOLIDAYS=new Set();let kickoffDate="";\n'+functions+'\n'+checks,encoding='utf-8');subprocess.run(['node',str(p)],check=True)
print('JavaScript syntax: 4 blocks passed; duplicate IDs: none')
