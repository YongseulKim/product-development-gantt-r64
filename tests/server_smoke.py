"""Run API checks against a temporary database, never production data."""
import copy, importlib.util, json, tempfile, threading, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gantt_server',ROOT/'server/server.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='gantt-qa-') as temp:
    m.DATA=Path(temp);m.DB=m.DATA/'projects.json';m.initialize()
    http=ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(http.server_port)
    def req(path,body=None,headers=None):
        h={'Content-Type':'application/json',**(headers or {})}
        request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=h)
        try:r=urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:r=error
        data=r.read();return r.status,json.loads(data) if 'application/json' in r.headers.get('Content-Type','') else data.decode()
    try:
        status,ls=req('/api/projects');check('initial project',status==200 and len(ls['projects'])==1)
        pid=ls['projects'][0]['id'];status,record=req('/api/projects/'+pid)
        check('read project',status==200 and bool(record['state']['tasks']))
        status,html=req('/');check('latest HTML served with server metadata',status==200 and 'window.GANTT_SERVER=' in html and 'ganttImportAsNew' in html)
        import re
        package=json.loads(re.search(r'<script id="embeddedGanttState" type="application/json">(.*?)</script>',html,re.S).group(1))
        check('embedded state matches database',json.loads(package['values']['product-development-gantt-v1'])==record['state']['tasks'])
        state=copy.deepcopy(record['state']);state['name']='QA temporary';state['notes']=[{'text':'<script> & 한글','time':'QA'}]
        status,new=req('/api/projects',{'state':state});check('create project',status==200 and new['state']==state)
        path='/api/projects/'+new['id'];old=new['version'];state['name']='QA saved'
        status,saved=req(path,{'version':old,'state':state});check('save project',status==200 and saved['state']==state)
        status,_=req(path,{'version':old,'state':state});check('stale save rejected',status==409)
        status,renamed=req(path+'/rename',{'version':saved['version'],'name':'QA renamed'});check('rename project',status==200 and renamed['state']['name']=='QA renamed')
        status,_=req(path+'/delete',{'version':saved['version']});check('stale delete rejected',status==409)
        invalid=copy.deepcopy(state);invalid['tasks'][0]['deps']=[invalid['tasks'][0]['id']]
        status,_=req('/api/projects',{'state':invalid});check('dependency cycle rejected',status==400)
        invalid=copy.deepcopy(state);invalid['tasks'][0]['deps']=['T999999']
        status,_=req('/api/projects',{'state':invalid});check('unknown dependency rejected',status==400)
        status,_=req('/api/projects',{'state':state},{'Origin':'http://example.invalid'});check('foreign origin rejected',status==403)
        status,_=req('/api/projects',{'state':state},{'Content-Type':'text/plain'});check('non JSON rejected',status==415)
        before=m.DB.read_bytes();m.initialize();check('reinitialize preserves database',m.DB.read_bytes()==before)
        status,deleted=req(path+'/delete',{'version':renamed['version']});check('delete project',status==200 and bool(deleted.get('deletedAt')))
        status,ls=req('/api/projects');check('deleted project hidden',status==200 and all(p['id']!=new['id'] for p in ls['projects']))
        status,_=req(path);check('deleted project inaccessible',status==404)
        status,_=req(path,{'version':deleted['version'],'state':state});check('deleted project cannot be saved',status==404)
        check('soft delete retained',any(p['id']==new['id'] and p.get('deletedAt') for p in m.read_db()['projects']))
        clock=m.datetime
        class FrozenClock:
            @staticmethod
            def now():return clock(2026,10,26,12,0,0)
        m.datetime=FrozenClock
        try:
            for _ in range(53):m.write_db(m.read_db())
        finally:m.datetime=clock
        check('backup retention 50 with identical timestamps',len(list((m.DATA/'project_backups').glob('*.json')))==50)
        check('stored notes preserved',next(p for p in m.read_db()['projects'] if p['id']==new['id'])['state']['notes']==state['notes'])
        print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
    finally:http.shutdown();http.server_close()
