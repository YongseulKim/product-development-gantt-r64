"""Real Chromium/WebDriver checks, with temporary server DB and browser profile."""
import base64,importlib.util,json,os,socket,subprocess,tempfile,threading,time,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from browser_environment import browser_environment
R=Path(__file__).resolve().parents[1];E=R/'docs/evidence';E.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('server',R/'server/server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=[]
def check(name,ok):
 assert ok,name
 checks.append(name);print('PASS',name,flush=True)
def http(url,data=None):
 req=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=45) as res:return json.load(res)
 except urllib.error.HTTPError as error:
  raise RuntimeError(error.read().decode()) from error
with tempfile.TemporaryDirectory(prefix='gantt-ui-') as temp:
 t=Path(temp);m.DATA=t/'data';m.DB=m.DATA/'projects.json';m.initialize()
 server=ThreadingHTTPServer(('127.0.0.1',0),m.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 chrome_binary,driver_binary,env=browser_environment(R)
 log=open(E/'design-v3-chromedriver.log','w');driver=subprocess.Popen([driver_binary,'--port='+str(port)],env=env,stdout=log,stderr=log)
 wd='http://127.0.0.1:'+str(port);sid=None
 try:
  for _ in range(100):
   try:http(wd+'/status');break
   except Exception:time.sleep(.1)
  caps={'browserName':'chrome','goog:chromeOptions':{'binary':chrome_binary,'args':['--headless','--no-sandbox','--disable-gpu','--window-size=1440,1000','--user-data-dir='+str(t/'profile')],'prefs':{'download.default_directory':str(t),'download.prompt_for_download':False}},'goog:loggingPrefs':{'browser':'ALL'}}
  sid=http(wd+'/session',{'capabilities':{'alwaysMatch':caps}})['value']['sessionId'];endpoint=wd+'/session/'+sid
  def call(path,data={}):return http(endpoint+path,data)['value']
  def js(script,*args):return call('/execute/sync',{'script':script,'args':list(args)})
  def click(selector):
   js("document.querySelector(arguments[0]).scrollIntoView({block:'center',inline:'nearest'})",selector)
   el=call('/element',{'using':'css selector','value':selector});call('/element/'+el['element-6066-11e4-a52e-4f735466cecf']+'/click')
  def wait(script,timeout=15):
   end=time.time()+timeout
   while time.time()<end:
    if js(script):return
    time.sleep(.2)
   raise AssertionError('Timeout: '+script)
  def screenshot(name):(E/name).write_bytes(base64.b64decode(http(endpoint+'/screenshot')['value']))
  call('/url',{'url':base});wait("return document.querySelector('#projectSelect').options.length>0")
  check('initial chart rendered',js("return document.querySelectorAll('#chart .bar').length>0"));screenshot('desktop-initial.png')
  wait("return document.fonts.status==='loaded'")
  check('embedded Pretendard loaded successfully',js("return [...document.fonts].some(f=>f.family.includes('Pretendard')&&f.status==='loaded')"))
  check('header conversation uses designer placement',js("return !!document.querySelector('header #ganttChatButton')"))
  click('#exclusionEditBtn')
  check('work actions portaled to body and visible inside desktop viewport',js("const m=document.querySelector('#workEditActions'),r=m.getBoundingClientRect();return !m.hidden&&m.parentElement===document.body&&getComputedStyle(m).position==='fixed'&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight"))
  screenshot('v3-work-edit-desktop.png')
  js("workEditSelection.add('T04');updateWorkEditActions()")
  click('#workEditExclude');check('floating exclusion action updates selected task',js("return tasks.find(t=>t.id==='T04').notApplicable"))
  js("workEditSelection.add('T04');updateWorkEditActions()")
  click('#workEditRestore');check('floating restore action includes selected task again',js("return !tasks.find(t=>t.id==='T04').notApplicable"))

  click('#addTaskBtn');check('portaled add task action opens form',js("return !document.querySelector('#addTaskForm').hidden"))
  js("document.querySelector('#addTaskForm').hidden=true")
  click('#workEditClose');check('work editing closes',js("return document.querySelector('#workEditActions').hidden&&!exclusionEdit"))
  call('/window/rect',{'width':1024,'height':768});click('#exclusionEditBtn')
  check('work actions stay inside smaller desktop viewport',js("const r=document.querySelector('#workEditActions').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight"))
  click('#workEditClose')
  logs=call('/log',{'type':'browser'});check('no font decode or JavaScript errors',not any(x['level']=='SEVERE' and 'favicon.ico' not in x['message'] for x in logs))
 finally:
  (E/'design-v3-results.json').write_text(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
  if sid:
   try:
    req=urllib.request.Request(wd+'/session/'+sid,method='DELETE');urllib.request.urlopen(req,timeout=10).close()
   except Exception:pass
  driver.terminate();driver.wait(timeout=10);log.close();server.shutdown();server.server_close()
