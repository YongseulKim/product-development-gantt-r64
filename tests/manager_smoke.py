"""Real source worker lifecycle, folder locking, presence and original save API."""
from pathlib import Path
import importlib.util,json,socket,sys,tempfile,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from manager_runtime import Presence, ServerProcess, ensure_assets
checks=[]
def check(name,value):
 assert value,name
 checks.append(name);print('PASS',name,flush=True)
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def http(url,data=None):
 req=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=6) as response:return json.load(response)
def ready(proc):
 end=time.monotonic()+15
 while time.monotonic()<end:
  if proc.log_path.exists():
   events=[json.loads(line) for line in proc.log_path.read_text().splitlines()]
   if any(e['type']=='ready' for e in events):return events
  if proc.process.poll() is not None:raise AssertionError(proc.log_path.read_text())
  time.sleep(.1)
 raise AssertionError('서버 시작 시간 초과')
p=Presence(timeout=60);p.beat('10.0.0.1','one',100);p.beat('10.0.0.1','two',110);check('same IP grouped across tabs',len(p.snapshot(120))==1);p.leave('10.0.0.1','one');check('leaving one tab keeps other tab',len(p.snapshot(121))==1);check('idle IP expires',not p.snapshot(171))
with tempfile.TemporaryDirectory(prefix='gantt-assets-') as temp:
 folder=Path(temp);(folder/'index.html').write_text('existing HTML');(folder/'initial_project.json').write_text('existing initial');ensure_assets(folder)
 check('existing HTML and initial data never overwritten',(folder/'index.html').read_text()=='existing HTML' and (folder/'initial_project.json').read_text()=='existing initial')
with tempfile.TemporaryDirectory(prefix='gantt-manager-') as temp:
 folder=Path(temp);proc=ServerProcess();other=ServerProcess();number=port();base=f'http://127.0.0.1:{number}'
 try:
  proc.start(folder,number);ready(proc);check('empty folder self-initializes',all((folder/name).exists() for name in ['index.html','initial_project.json','data/projects.json']))
  with urllib.request.urlopen(base) as response:check('HTML receives heartbeat script',b'gantt-manager-presence' in response.read())
  http(base+'/api/server/heartbeat?tab=one');http(base+'/api/server/heartbeat?tab=two');time.sleep(.7)
  check('presence file exposes visitor IP',json.loads(proc.log_path.with_suffix('.presence.json').read_text())[0]['ip']=='127.0.0.1')
  for tab in ['one','two']:
   request=urllib.request.Request(base+'/api/server/leave',data=('tab='+tab).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
   with urllib.request.urlopen(request,timeout=3) as response:check('leave request accepted '+tab,response.status==200)
  time.sleep(.7);check('closed browser tabs removed from IP list',json.loads(proc.log_path.with_suffix('.presence.json').read_text())==[])
  record=http(base+'/api/projects/'+http(base+'/api/projects')['projects'][0]['id']);record['state']['notes'].append({'text':'서버 관리자 검수','time':'검수'})
  saved=http(base+'/api/projects/'+record['id'],{'version':record['version'],'state':record['state']});check('existing save API preserved',saved['state']['notes'][-1]['text']=='서버 관리자 검수')
  other.start(folder,port());other.process.wait(timeout=10);check('same folder rejects a second worker',other.process.returncode!=0 and '이미 실행 중' in other.log_path.read_text())
  check('graceful stop completes',proc.stop() is False and proc.process.poll()==0)
  proc.start(folder,number);ready(proc);check('restart retains saved state',http(base+'/api/projects/'+record['id'])['state']['notes'][-1]['text']=='서버 관리자 검수')
  check('Korean request logs',any('상품 저장 완료' in e['message'] for path in (folder/'logs').glob('*.jsonl') for e in map(json.loads,path.read_text().splitlines())))
  check('heartbeat requests do not flood logs',not any('heartbeat' in path.read_text() for path in (folder/'logs').glob('*.log')))
 finally:other.emergency_stop();proc.stop()
print(json.dumps({'passed':len(checks)},ensure_ascii=False))
