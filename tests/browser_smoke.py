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
 log=open(E/'chromedriver.log','w');driver=subprocess.Popen([driver_binary,'--port='+str(port)],env=env,stdout=log,stderr=log)
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
  click('#tableTab');check('table tab',js("return !document.querySelector('#tableView').hidden && document.querySelector('#tableTab').getAttribute('aria-selected')==='true'"));click('#chartTab')
  # Migrate only identifiable legacy sale-system notes; preserve task/user notes.
  migration=js("""const legacy=structuredClone(tasks),owner=legacy.find(t=>t.id==='T01'),prep=legacy.find(t=>t.id==='T33');delete owner.saleDetails;owner.saleDate=dateAt(BASE+105);owner.saleConfirmed=true;owner.events=[{id:'legacy-user',note:'상품안 사용자 메모'}];owner.scheduleChanges=[{id:'sale-legacy',text:prep.name+' 일정이 변경되었습니다.',time:'2026-10-23T00:00:00Z',acknowledged:true},{id:'sale-explicit',text:'옛 업무 일정이 변경되어 판매개시일이 변경되었습니다.',time:'2026-10-23T00:00:00Z',acknowledged:false},{id:'task-legacy',text:'상품안 검토 자체의 기록',time:'2026-10-23T00:00:00Z',acknowledged:false}];const normalized=normalizeTasks(legacy),root=normalized.find(t=>t.id==='T01'),sale=meetingRecord('ready',normalized);return {taskNotes:root.scheduleChanges.map(n=>n.id),saleNotes:sale.scheduleChanges,events:root.events,saleDate:sale.saleDate,confirmed:sale.saleConfirmed,idempotent:JSON.stringify(normalizeTasks(normalized))===JSON.stringify(normalized),legacyRemoved:!('saleDate' in root)}""")
  check('legacy sale notes separated without losing task notes',migration['taskNotes']==['task-legacy'] and [n['id'] for n in migration['saleNotes']]==['sale-legacy','sale-explicit'])
  check('migration preserves user notes dates confirmation and acknowledgement',migration['events'][0]['note']=='상품안 사용자 메모' and migration['saleDate'] and migration['confirmed'] and migration['saleNotes'][0]['acknowledged'] and migration['legacyRemoved'])
  check('sale migration is idempotent',migration['idempotent'])
  js("tasks=normalizeTasks([...tasks,{id:'T88001',name:'검수용 판매준비',dept:'검수',type:'prep',customTask:true,start:BASE+100,end:BASE+101,deps:[],done:false}]);meetingRecord('ready').saleDate=dateAt(BASE+105);meetingRecord('ready').saleConfirmed=false;store.setItem(CACHE,JSON.stringify(tasks));render()")
  review_before=js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")
  js("quickDuration({dataset:{id:'T88001'},value:'2'})")
  check('prep change writes only to sale memo collection',js("return meetingRecord('ready').scheduleChanges.some(n=>n.text.includes('검수용 판매준비'))") and js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")==review_before)
  js("showTask('T01')")
  check('task drawer hides sale-system notes',js("return !document.querySelector('.memo-entries').textContent.includes('검수용 판매준비')"))
  js('closeTaskDrawer()');click('#readyCard')
  check('sale detail displays sale-system notes',js("return document.querySelector('.memo-entries').textContent.includes('검수용 판매준비')"))
  js("document.querySelector('#memoBody').value='판매개시 전용 사용자 메모'");click('#eventSave')
  check('sale user memo stays separate from task user memos',js("return meetingRecord('ready').events.some(e=>e.note==='판매개시 전용 사용자 메모')&&!tasks.find(t=>t.id==='T01').events.some(e=>e.note==='판매개시 전용 사용자 메모')"))
  sale_note_id=js("return meetingRecord('ready').scheduleChanges.find(n=>n.text.includes('검수용 판매준비')).id")
  js("document.querySelector('[data-delete-memo=\"'+CSS.escape(arguments[0])+'\"][data-memo-kind=\"system\"]').click()",sale_note_id)
  check('sale-system memo deletion is isolated',js("return !meetingRecord('ready').scheduleChanges.some(n=>n.id===arguments[0])",sale_note_id) and js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")==review_before)
  click('#undoBtn');check('undo restores sale-system memo',js("return meetingRecord('ready').scheduleChanges.some(n=>n.id===arguments[0])",sale_note_id))
  js('closeBreakdown()')
  # Open an actual task via a chart bar; snapshot state only for assertions.
  before=js('return structuredClone(tasks)');tid=before[0]['id']
  js("showTask(arguments[0])",tid);click('#drawerComplete');check('complete task',js('return tasks.find(t=>t.id===arguments[0]).done',tid))
  click('#undoBtn');check('undo completion',js('return !tasks.find(t=>t.id===arguments[0]).done',tid));click('#redoBtn');check('redo completion',js('return tasks.find(t=>t.id===arguments[0]).done',tid));click('#undoBtn')
  js('closeTaskDrawer()');click('#exclusionEditBtn');click('#addTaskBtn');js("document.querySelector('#newName').value='QA <script> & 업무';document.querySelector('#newDept').value='__custom__';document.querySelector('#newDept').dispatchEvent(new Event('change'));document.querySelector('#newDeptCustom').value='검수부서'")
  click('#addTaskForm button[type=submit]')
  try:call('/alert/accept',{})
  except RuntimeError as error:
   if 'no such alert' not in str(error):raise
  check('add custom task',js("return tasks.some(t=>t.name==='QA <script> & 업무')"))
  added=js("return structuredClone(tasks.find(t=>t.name==='QA <script> & 업무'))");check('custom name displayed as text',js("return Array.from(document.querySelectorAll('#chart .bar-text')).some(e=>e.textContent.includes('QA <script> & 업무') && !e.querySelector('script'))"))
  js('showTask(arguments[0])',added['id']);click('#drawerEdit');js("const e=document.querySelector('#inlineDuration');e.value='4';e.dispatchEvent(new Event('input'))")
  click('#inlineEditor button[type=submit]');check('edit task duration',js('return tasks.find(t=>t.id===arguments[0]).end-tasks.find(t=>t.id===arguments[0]).start===4',added['id']))
  # Both memo types may have the same ID; deletion must target only its own collection.
  js("const t=tasks.find(t=>t.id===arguments[0]);t.events.push({id:'qa-collision',note:'사용자 보존',createdAt:new Date().toISOString()});t.scheduleChanges=[{id:'qa-collision',text:'시스템 삭제 검수',time:new Date().toISOString(),acknowledged:true}];showTask(t.id)",added['id'])
  click('[data-delete-memo="qa-collision"][data-memo-kind="system"]')
  check('delete system memo preserves user memo',js("const t=tasks.find(t=>t.id===arguments[0]);return !t.scheduleChanges.some(m=>m.id==='qa-collision')&&t.events.some(m=>m.id==='qa-collision')",added['id']))
  click('#undoBtn');check('undo system memo deletion',js("return tasks.find(t=>t.id===arguments[0]).scheduleChanges.some(m=>m.id==='qa-collision')",added['id']))
  click('#redoBtn');check('redo system memo deletion',js("return !tasks.find(t=>t.id===arguments[0]).scheduleChanges.some(m=>m.id==='qa-collision')",added['id']))
  js('showTask(arguments[0])',added['id']);click('[data-delete-memo="qa-collision"][data-memo-kind="user"]')
  check('user memo deletion still works',js("return !tasks.find(t=>t.id===arguments[0]).events.some(m=>m.id==='qa-collision')",added['id']))
  js('closeTaskDrawer()');click('#exclusionEditBtn');click('#projectSave');wait("return document.querySelector('#projectStatus')?.textContent.includes('저장 완료') || document.body.innerText.includes('서버 저장 완료')")
  saved=js('return structuredClone(tasks)');call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0");(E/'save-comparison.json').write_text(json.dumps({'before':saved,'after':js('return structuredClone(tasks)')},ensure_ascii=False,indent=2));check('server save survives refresh',js('return structuredClone(tasks)')==saved)
  click('#htmlMenuBtn');click('#saveHtmlBtn')
  for _ in range(100):
   files=list(t.glob('*.html'))
   if files:break
   time.sleep(.1)
  check('HTML downloaded',bool(files));download=files[0]
  call('/url',{'url':download.as_uri()});wait('return typeof tasks!=="undefined" && tasks.length>0')
  check('download reopens with same tasks',js('return structuredClone(tasks)')==saved);check('export strips server metadata',js('return !window.GANTT_SERVER'))
  check('special characters preserved',js("return tasks.some(t=>t.name==='QA <script> & 업무')"))
  call('/url',{'url':base});wait("return document.querySelector('#projectSelect').options.length>0")
  # WebDriver file upload to the real file input.
  el=call('/element',{'using':'css selector','value':'#loadHtmlInput'})['element-6066-11e4-a52e-4f735466cecf']
  call('/element/'+el+'/value',{'text':str(download),'value':list(str(download))})
  wait("return document.querySelector('#projectSelect').options.length===2")
  check('HTML import creates new server project',len(http(base+'/api/projects')['projects'])==2)
  check('HTML import preserves tasks',js('return structuredClone(tasks)')==saved)
  # Sale-date changes must round-trip without leaking state into task memos.
  js("activeMilestone='ready';render();document.querySelector('#meetingDate').value=dateAt(BASE+110);document.querySelector('#meetingConfirmed').checked=false")
  sale_task_before=js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")
  click('#meetingSave')
  check('sale date edit keeps task memos separate',js("return meetingRecord('ready').saleDate===dateAt(BASE+110)&&JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)===arguments[0]",sale_task_before))
  sale_state=js('return structuredClone(tasks)');js('closeBreakdown()');click('#projectSave');wait("return document.querySelector('#projectStatus').textContent.includes('서버 저장 완료')")
  call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0")
  check('sale date and both memo collections survive reload',js('return structuredClone(tasks)')==sale_state)
  call('/window/rect',{'width':390,'height':844});time.sleep(.5);screenshot('mobile-390.png')
  check('mobile date cards do not overlap',js("const c=[...document.querySelectorAll('#stats .stat')];return c.every((e,i)=>!i||e.getBoundingClientRect().top>=c[i-1].getBoundingClientRect().bottom) && c.every(e=>e.scrollWidth<=e.clientWidth)"))
  check('mobile chat opens',js("document.querySelector('#ganttChatButton').click();return !document.querySelector('#ganttChatPanel').hidden"))
  click('#ganttChatClose');check('mobile chat closes',js("return document.querySelector('#ganttChatPanel').hidden"))
  logs=call('/log',{'type':'browser'});(E/'browser-console.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2))
  severe=[x for x in logs if x['level']=='SEVERE' and 'favicon.ico' not in x['message']]
  check('no severe browser errors',not severe)
 finally:
  (E/'browser-results.json').write_text(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
  if sid:
   try:
    req=urllib.request.Request(wd+'/session/'+sid,method='DELETE');urllib.request.urlopen(req,timeout=10).close()
   except Exception:pass
  driver.terminate();driver.wait(timeout=10);log.close();server.shutdown();server.server_close()
