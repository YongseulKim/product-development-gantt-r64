"""Product Gantt server. Python 3.9+, standard library only."""
import argparse, json, os, re, shutil, socket, threading, uuid
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
LOCK=threading.RLock()
DB=DATA/'projects.json'
def read_db():
    return json.loads(DB.read_text(encoding='utf-8'))
def write_db(db):
    DATA.mkdir(exist_ok=True)
    tmp=DATA/'projects.tmp'
    tmp.write_text(json.dumps(db,ensure_ascii=False,indent=2),encoding='utf-8')
    if DB.exists():
        backups=DATA/'project_backups';backups.mkdir(exist_ok=True)
        shutil.copy2(DB,backups/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex+'.json'))
        for p in sorted(backups.glob('*.json'))[:-50]:p.unlink()
    os.replace(tmp,DB)
def new_record(state):
    return {'id':uuid.uuid4().hex,'version':uuid.uuid4().hex,'savedAt':datetime.now().astimezone().isoformat(),'state':state}
def initialize():
    if DB.exists():return
    projects=[]
    old=DATA/'schedule.json'
    if old.exists():
        previous=json.loads(old.read_text(encoding='utf-8')).get('state')
        if previous:
            previous.setdefault('name','기존 서버 일정');previous.setdefault('notes',[]);previous.setdefault('initialMessages',[])
            validate(previous);projects.append(new_record(previous))
    initial=json.loads((ROOT/'initial_project.json').read_text(encoding='utf-8'));validate(initial)
    projects.append(new_record(initial));write_db({'projects':projects})
def validate(state):
    if not isinstance(state, dict) or not isinstance(state.get('tasks'), list):
        raise ValueError('Invalid schedule')
    tasks = state['tasks']
    if len(tasks) > 5000:
        raise ValueError('Too many tasks')
    ids = set()
    for t in tasks:
        if not isinstance(t, dict) or not isinstance(t.get('id'), str) or t['id'] in ids:
            raise ValueError('Invalid task ID')
        ids.add(t['id'])
        if not all(isinstance(t.get(k), str) for k in ('name', 'dept', 'type')):
            raise ValueError('Invalid task fields')
        if not all(type(t.get(k)) is int for k in ('start', 'end')) or t['end'] <= t['start']:
            raise ValueError('Invalid dates')
        if not isinstance(t.get('deps'), list) or not all(isinstance(d, str) for d in t['deps']):
            raise ValueError('Invalid dependencies')
    if any(d not in ids for t in tasks for d in t['deps']):
        raise ValueError('Unknown dependency')
    pending = {t['id']: set(t['deps']) for t in tasks}
    while pending:
        ready = {i for i, deps in pending.items() if not deps}
        if not ready:
            raise ValueError('Dependency cycle')
        pending = {i: deps-ready for i, deps in pending.items() if i not in ready}
    datetime.strptime(state.get('kickoffDate', ''), '%Y-%m-%d')
    if not isinstance(state.get('holidayText'), str):
        raise ValueError('Invalid holidays')


_validate_schedule=validate
def validate(state):
    _validate_schedule(state)
    if not isinstance(state.get('name'),str) or not 0<len(state['name'].strip())<=100:raise ValueError('Invalid name')
    for key in ('notes','initialMessages'):
        if not isinstance(state.get(key,[]),list):raise ValueError('Invalid messages')
    if any(not isinstance(n,dict) or not isinstance(n.get('text'),str) or not isinstance(n.get('time'),str) for n in state.get('notes',[])):raise ValueError('Invalid notes')
    if any(not isinstance(m,str) for m in state.get('initialMessages',[])):raise ValueError('Invalid messages')
    if any(t['start'] < -415 or t['end']>315 or not re.fullmatch(r'T\d+',t['id']) or t['type'] not in ('plan','build','review','prep') for t in state['tasks']):raise ValueError('Invalid tasks')
def json_script(value):return json.dumps(value,ensure_ascii=False).replace('<','\\u003c')
def page(record,draft=False):
    s=record['state'];values={'product-development-gantt-v1':json.dumps(s['tasks'],ensure_ascii=False),'product-development-kickoff-v1':s['kickoffDate'],'product-development-holidays-v1':s['holidayText'],'product-development-stage-order-v1':str(s.get('respectMilestones',False)).lower(),'product-development-name-v1':s['name'],'product-development-chat-v1':json.dumps(s.get('notes',[]),ensure_ascii=False),'product-development-chat-initial-v1':json.dumps(s.get('initialMessages',[]),ensure_ascii=False)}
    package={'format':'product-development-gantt','version':1,'id':record['id'],'values':values}
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    html=re.sub(r'<script id="embeddedGanttState" type="application/json">.*?</script>',lambda m:'<script id="embeddedGanttState" type="application/json">'+json_script(package)+'</script>',html,flags=re.S)
    meta={k:record[k] for k in ('id','version')};meta['draft']=draft
    return html.replace('<head>','<head><script id="ganttServerMeta">window.GANTT_SERVER='+json_script(meta)+';</script>',1).encode('utf-8')
class Handler(BaseHTTPRequestHandler):
    def reply(self,status,value,mime='application/json; charset=utf-8'):
        data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        url=urlsplit(self.path)
        try:
            with LOCK:db=read_db()
            db['projects']=[p for p in db['projects'] if not p.get('deletedAt')]
            if url.path=='/api/projects':return self.reply(200,{'projects':[{'id':p['id'],'name':p['state']['name'],'savedAt':p['savedAt']} for p in db['projects']]})
            if url.path in ('/','/index.html'):
                if not db['projects']:
                    initial=json.loads((ROOT/'initial_project.json').read_text(encoding='utf-8'))
                    initial['name']='새 상품'
                    return self.reply(200,page(new_record(initial),draft=True),'text/html; charset=utf-8')
                id=parse_qs(url.query).get('project',[db['projects'][0]['id']])[0]
                record=next((p for p in db['projects'] if p['id']==id),None)
                if record:return self.reply(200,page(record),'text/html; charset=utf-8')
            if url.path.startswith('/api/projects/'):
                record=next((p for p in db['projects'] if p['id']==url.path.rsplit('/',1)[1]),None)
                if record:return self.reply(200,record)
            self.reply(404,{'error':'상품 일정을 찾을 수 없습니다.'})
        except (OSError,ValueError,KeyError):self.reply(500,{'error':'서버 데이터 읽기에 실패했습니다.'})
    def manage_project(self):
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):return self.reply(403,{'error':'Origin rejected'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'JSON required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=10000:return self.reply(413,{'error':'Request too large'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError()
            action=self.path.rsplit('/',1)[1];project_id=self.path.split('/')[3]
            if action=='rename':
                name=body.get('name')
                if not isinstance(name,str) or not 0<len(name.strip())<=100:raise ValueError()
        except (ValueError,TypeError):return self.reply(400,{'error':'상품명은 1~100자로 입력해 주세요.'})
        with LOCK:
            try:
                db=read_db();record=next((p for p in db['projects'] if p['id']==project_id and not p.get('deletedAt')),None)
                if not record or record.get('deletedAt'):return self.reply(404,{'error':'상품을 찾을 수 없습니다.'})
                if body.get('version')!=record['version']:return self.reply(409,{'error':'다른 사용자가 변경했습니다. 새로고침 후 다시 시도해 주세요.'})
                if action=='rename':record['state']['name']=name.strip()
                else:record['deletedAt']=datetime.now().astimezone().isoformat()
                record.update(version=uuid.uuid4().hex,savedAt=datetime.now().astimezone().isoformat())
                write_db(db)
            except (OSError,ValueError):return self.reply(500,{'error':'변경을 저장하지 못했습니다.'})
        return self.reply(200,record)
    def do_POST(self):
        if re.fullmatch(r'/api/projects/[a-f0-9]{32}/(?:rename|delete)',self.path):return self.manage_project()
        if not re.fullmatch(r'/api/projects(?:/[a-f0-9]{32})?',self.path):return self.reply(404,{'error':'Not found'})
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):return self.reply(403,{'error':'Origin rejected'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'JSON required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=5_000_000:return self.reply(413,{'error':'Request too large'})
            body=json.loads(self.rfile.read(length));validate(body.get('state'))
        except (ValueError,TypeError,AttributeError,KeyError):return self.reply(400,{'error':'일정 데이터 형식이 올바르지 않습니다.'})
        with LOCK:
            try:
                db=read_db()
                if self.path=='/api/projects':
                    record=new_record(body['state']);db['projects'].append(record)
                else:
                    record=next((p for p in db['projects'] if p['id']==self.path.rsplit('/',1)[1]),None)
                    if not record or record.get('deletedAt'):return self.reply(404,{'error':'상품을 찾을 수 없습니다.'})
                    if body.get('version')!=record['version']:return self.reply(409,{'error':'다른 사용자가 먼저 저장했습니다. HTML로 내 변경을 보관한 후 새로고침하세요.'})
                    record.update(version=uuid.uuid4().hex,savedAt=datetime.now().astimezone().isoformat(),state=body['state'])
                write_db(db)
            except (OSError,ValueError):return self.reply(500,{'error':'저장 실패. 서버 데이터 폴더를 확인하세요.'})
        self.reply(200,record)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);args=parser.parse_args();initialize()
    print('Open: http://localhost:%d'%args.port)
    for ip in sorted(set(socket.gethostbyname_ex(socket.gethostname())[2])):print('Share: http://%s:%d'%(ip,args.port))
    print('Keep this window open. Data:',DATA)
    try:ThreadingHTTPServer(('0.0.0.0',args.port),Handler).serve_forever()
    except KeyboardInterrupt:pass
