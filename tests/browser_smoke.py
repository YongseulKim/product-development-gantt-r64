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
  click('#tableTab');check('table tab',js("return !document.querySelector('#tableView').hidden && document.querySelector('#tableTab').getAttribute('aria-selected')==='true'"));click('#chartTab')
  rule_checks=js("""const list=structuredClone(tasks),m2=meetingRecord('m2',list);for(const t of list)if(!t.meetingKind){t.start=BASE;t.end=BASE+1}m2.start=BASE+80;m2.end=m2.start+1;const checks=[];const test=(name,ok)=>checks.push({name,ok});
  const at=n=>dateAt(m2.start+n),error=n=>meetingProblems('m3',at(n),list);
  test('committee permits exactly five business days',error(5).length===0);test('committee blocks four business days',error(4).length===1&&error(4)[0].includes('5영업일'));
  test('standard and default committee schedules use five days',meetingDefaultOffset('m3',list)===m2.start+5&&seed.find(t=>t.id===MEETING_IDS.m3).start-seed.find(t=>t.id===MEETING_IDS.m2).start===5);
  const required=requiredFor('m3',list);required[0].end=m2.start+8;required[1].end=m2.start+10;
  test('committee gap message precedes task deadline message',error(4).length===1&&error(4)[0].includes('5영업일')&&!error(4)[0].includes(required[1].name));
  test('only latest required task appears in deadline message',error(5).length===1&&error(5)[0].includes(required[1].name)&&!error(5)[0].includes(required[0].name));
  let holiday=at(4);while(isWorkday(new Date(holiday+'T12:00:00')))holiday=nextCalendarDay(holiday);
  test('holiday message takes precedence over all other errors',meetingProblems('m3',holiday,list).join('')==='휴일은 선택할 수 없습니다. 날짜를 조정해 주세요.');
  for(const kind of ['m2','ready']){const req=requiredFor(kind,list);req[0].end=m2.start+8;req[1].end=m2.start+10;const errors=meetingProblems(kind,at(5),list);test(kind+' shows only latest required task',errors.length===1&&errors[0].includes(req[1].name)&&!errors[0].includes(req[0].name))}
  for(const type of ['plan','build','review','prep']){const custom={id:'T99090',name:'선택 업무',dept:'검수',type,customTask:true,start:BASE+200,end:BASE+201,deps:[]},next=normalizeTasks([...list,custom]);test(type+' custom task never becomes required',['m2','m3','ready'].every(k=>!requiredFor(k,next).some(t=>t.id===custom.id)));test(type+' custom task does not move milestones',JSON.stringify(applyAddedTask(list,next,custom))===JSON.stringify(next))}
  const base=structuredClone(list);for(const t of base){t.deps=[];if(!t.meetingKind){t.start=BASE;t.end=BASE+1;t.done=false}}const a=meetingRecord('m2',base),b=meetingRecord('m3',base);a.start=BASE+80;a.end=a.start+1;b.start=a.start+5;b.end=b.start+1;const edited=structuredClone(base);edited.find(t=>t.id==='T05').end=BASE+82;const result=propagateSuccessors(base,edited,['T05']).tasks;test('propagated committee date uses five-day gap',meetingRecord('m3',result).start-meetingRecord('m2',result).start===5);
  test('sale default is ten business days after committee',estimatedSaleDate()===dateAt(meetingRecord('m3').start+10));
  const original=structuredClone(tasks);for(const t of requiredFor('ready',original)){t.start=BASE;t.end=BASE+1}const committee=meetingRecord('m3',original);committee.start=BASE+80;committee.end=committee.start+1;const sale=meetingRecord('ready',original);sale.saleDate='';test('missing sale date falls back to ten business days',meetingDateValue('ready',original)===dateAt(committee.start+10));sale.saleDate=dateAt(BASE+91);sale.saleConfirmed=true;const originalJSON=JSON.stringify(original),next=structuredClone(original),newCommittee=meetingRecord('m3',next);newCommittee.start=BASE+84;newCommittee.end=newCommittee.start+1;updateSaleFromChanges(original,next);
  test('committee delay propagates sale at ten business days',meetingRecord('ready',next).saleDate===dateAt(BASE+94));test('moved sale loses confirmation without changing original data',!meetingRecord('ready',next).saleConfirmed&&JSON.stringify(original)===originalJSON);
  const delayed=structuredClone(next);requiredFor('ready',delayed)[0].end=BASE+110;updateSaleFromChanges(next,delayed);test('later required prep deadline still takes precedence',meetingRecord('ready',delayed).saleDate===dateAt(BASE+110));
  const later=structuredClone(original);meetingRecord('ready',later).saleDate=dateAt(BASE+150);const laterNext=structuredClone(later);meetingRecord('m3',laterNext).start=BASE+84;meetingRecord('m3',laterNext).end=BASE+85;updateSaleFromChanges(later,laterNext);test('existing later sale date and confirmation are retained',meetingRecord('ready',laterNext).saleDate===dateAt(BASE+150)&&meetingRecord('ready',laterNext).saleConfirmed);
  return checks;""")
  for item in rule_checks:check(item['name'],item['ok'])
  # Excluded requirements are folded without hiding completed, applicable work.
  required_before=js('return structuredClone(tasks)')
  js("const first=tasks.find(t=>t.id==='T08');first.start=BASE+150;first.end=BASE+160;first.deps=[];tasks.find(t=>t.id==='T13').done=true;tasks.find(t=>t.id==='T16').notApplicable=true;const committee=meetingRecord('m3');committee.requiredExclusions=['T08'];committee.start=Math.max(meetingRecord('m2').start+COMMITTEE_GAP,...requiredFor('m3').map(t=>t.end))+2;committee.end=committee.start+1;committee.confirmedDate='';activeMilestone='m3';render()")
  required_date=js("return document.querySelector('#meetingDate').value")
  required_order=js("return [...document.querySelectorAll('.meeting-candidates > .meeting-required-row [data-meeting-task]')].map(e=>e.dataset.meetingTask)")
  check('excluded required tasks are initially folded',js("const g=document.querySelector('.excluded-requirements');return g&&!g.open&&g.querySelectorAll('.meeting-required-row').length===2&&!document.querySelector('.meeting-candidates > .requirement-excluded')"))
  check('completed applicable requirements remain visible',js("return [...document.querySelectorAll('.meeting-candidates > .meeting-required-row [data-meeting-task]')].some(e=>e.dataset.meetingTask==='T13')"))
  check('folded exclusions do not block valid meeting date',js("return !document.querySelector('#meetingSave').disabled&&!document.querySelector('#meetingError').textContent"))
  screenshot('excluded-requirements-collapsed.png')
  click('.excluded-requirements > summary');click('[data-required-key="T08"]')
  check('restoring requirement moves it to main list and revalidates deadline',js("return !!document.querySelector('.meeting-candidates > .meeting-required-row [data-required-key=T08]')&&document.querySelector('#meetingSave').disabled&&document.querySelector('#meetingError').textContent.includes(tasks.find(t=>t.id==='T08').name)"))
  check('moving requirement preserves unsaved meeting date',js("return document.querySelector('#meetingDate').value")==required_date)
  click('[data-required-key="T08"]')
  check('excluding again clears deadline error and preserves expansion',js("return document.querySelector('.excluded-requirements').open&&!document.querySelector('#meetingSave').disabled"))
  click('[data-required-key="T13"]');click('[data-required-key="T13"]')
  check('repeated exclusion and restoration retain task order and handlers',js("return [...document.querySelectorAll('.meeting-candidates > .meeting-required-row [data-meeting-task]')].map(e=>e.dataset.meetingTask)")==required_order)
  js("document.querySelectorAll('[data-required-key]').forEach(input=>{if(!input.disabled&&!input.checked)input.click()})")
  check('all excluded state shows explicit empty main list',js("return !document.querySelector('.meeting-candidates > .meeting-required-row')&&document.querySelector('.required-empty').textContent.includes('적용 대상')"))
  click('#meetingSave')
  check('saving includes folded checkboxes and preserves global exclusion',js("return requiredFor('m3').length===0&&tasks.find(t=>t.id==='T16').notApplicable&&!document.querySelector('.excluded-requirements').open"))
  click('#undoBtn');check('undo restores original required list and completed state',js("return requiredFor('m3').length>0&&tasks.find(t=>t.id==='T13').done&&meetingRecord('m3').requiredExclusions.join(',')==='T08'"))
  click('#redoBtn');check('redo restores excluded requirements',js("return requiredFor('m3').length===0"))
  excluded_saved=js('return structuredClone(tasks)');js('closeBreakdown()');click('#projectSave');wait("return document.querySelector('#projectStatus').textContent.includes('서버 저장 완료')")
  call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0")
  check('folded requirements persist after server save and reload',js('return structuredClone(tasks)')==excluded_saved)
  js("tasks=arguments[0];undoStack.length=0;redoStack.length=0;store.setItem(CACHE,JSON.stringify(tasks));activeMilestone=null;render();updateHistoryButtons()",required_before)
  # New independent rounds support alternating net/gross premium work without inherited links.
  independent_before=js('return structuredClone(tasks)')
  js("tasks.find(t=>t.id==='T04').done=true;tasks.find(t=>t.id==='T05').done=true;showTask('T04')")
  existing_before_add=js('return JSON.stringify(tasks)');independent_count=js('return tasks.length')
  click('#addRound');js("document.querySelector('#roundStart').value=dateAt(BASE+100);document.querySelector('#roundEnd').value=dateAt(BASE+100)");click('#roundForm button[type=submit]')
  net_second=js("return roundFamily(tasks.find(t=>t.id==='T04')).at(-1).id")
  check('net-premium second round starts with no predecessor or inherited relation kinds',js("const t=tasks.find(t=>t.id===arguments[0]);return t.independentRound&&t.deps.length===0&&Object.keys(t.dependencyKinds).length===0",net_second))
  check('adding one round does not auto-create gross-premium or downstream rounds',js("return tasks.length===arguments[0]+1&&roundFamily(tasks.find(t=>t.id==='T05')).length===1",independent_count))
  check('new round creation leaves every existing schedule memo and meeting unchanged',js('return JSON.stringify(tasks.filter(t=>t.id!==arguments[0]))',net_second)==existing_before_add)
  check('old gross-premium first round keeps net-premium first-round reference',js("return effectiveEdges(tasks.find(t=>t.id==='T05')).some(e=>e.task.id==='T04')&&!effectiveEdges(tasks.find(t=>t.id==='T05')).some(e=>e.task.id===arguments[0])",net_second))
  js("showTask('T05')");click('#addRound');js("document.querySelector('#roundStart').value=dateAt(BASE+110);document.querySelector('#roundEnd').value=dateAt(BASE+110)");click('#roundForm button[type=submit]')
  gross_second=js("return roundFamily(tasks.find(t=>t.id==='T05')).at(-1).id")
  check('gross-premium second round can be added independently too',js("const t=tasks.find(t=>t.id===arguments[0]);return tasks.length===arguments[1]+2&&t.independentRound&&t.deps.length===0",gross_second,independent_count))
  check('milestone requirements still use latest standard gross-premium round',js("return requiredFor('m2').some(t=>t.id===arguments[0])",gross_second))
  check('explicit independent-round references remain pinned when a later round exists',js("const t=tasks.find(t=>t.id===arguments[0]),later={...structuredClone(t),id:'T95999',branchNo:3,name:'검수용 이후 차수'},list=[...tasks,later],probe={id:'T95998',deps:[t.id],dependencyKinds:{}};return effectiveEdges(probe,list)[0].task.id===t.id",net_second))
  check('old unflagged round references retain legacy latest-round behavior',js("const root={id:'T96001',name:'과거 선행',dept:'검수',type:'build',customTask:true,start:BASE+30,end:BASE+31,deps:[],done:true},child={id:'T96002',name:'과거 후행',dept:'검수',type:'build',customTask:true,start:BASE+31,end:BASE+32,deps:[root.id],done:true},original=normalizeTasks([...tasks,root,child]),legacy={...structuredClone(original.find(t=>t.id===root.id)),id:'T96003',roundRootId:root.id,sourceId:root.id,branchNo:2,name:'과거 선행 [2차]',start:BASE+40,end:BASE+41,done:false,independentRound:false},next=normalizeTasks([...original,legacy]),result=propagateSuccessors(original,next,[legacy.id]);return effectiveEdges(next.find(t=>t.id===child.id),next)[0].task.id===legacy.id&&result.created.some(id=>result.tasks.find(t=>t.id===id).roundRootId===child.id)"))
  independent_others=js('return JSON.stringify(tasks.filter(t=>t.id!==arguments[0]))',net_second)
  js('showTask(arguments[0])',net_second);click('#drawerEdit');js("document.querySelector('#inlineStart').value=dateAt(BASE+1);document.querySelector('#inlineDuration').value='2'");click('#inlineEditor button[type=submit]')
  check('independent round can be scheduled without old predecessor date constraints',js("const t=tasks.find(t=>t.id===arguments[0]);return !document.querySelector('#inlineEditor')&&t.start===BASE+1&&t.end===BASE+3&&t.deps.length===0",net_second))
  check('editing net-premium second round does not move or notify other rounds',js('return JSON.stringify(tasks.filter(t=>t.id!==arguments[0]))',net_second)==independent_others)
  check('upstream edits do not attach empty-predecessor rounds',js("const before=tasks.filter(t=>[arguments[0],arguments[1]].includes(t.id)),root=tasks.find(t=>t.id==='T36'),result=cascadeEdit(tasks,root.id,root.start,root.end-root.start+2,root.deps);return before.every(t=>JSON.stringify(result.tasks.find(v=>v.id===t.id))===JSON.stringify(t))",net_second,gross_second))
  check('process migration and repeated normalization preserve independent empty predecessors',js("const input=structuredClone(tasks);input.forEach(t=>t.processVersion=0);const next=normalizeTasks(input);return [arguments[0],arguments[1]].every(id=>{const t=next.find(v=>v.id===id);return t.independentRound&&t.deps.length===0&&Object.keys(t.dependencyKinds).length===0})",net_second,gross_second))
  js('showTask(arguments[0])',net_second);deletion_snapshot=js('return JSON.stringify(tasks)');click('#deleteRound');call('/alert/accept',{})
  check('independent round deletion preserves unrelated independent rounds',js("return !tasks.some(t=>t.id===arguments[0])&&tasks.find(t=>t.id===arguments[1]).independentRound&&tasks.find(t=>t.id===arguments[1]).deps.length===0",net_second,gross_second))
  click('#undoBtn');check('undo restores independent round and its empty links',js('return JSON.stringify(tasks)')==deletion_snapshot)
  js('closeTaskDrawer()');click('#projectSave');wait("return document.querySelector('#projectStatus').textContent.includes('서버 저장 완료')");independent_saved=js('return structuredClone(tasks)');call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0")
  check('independent round markers and links persist after server reload',js('return structuredClone(tasks)')==independent_saved)
  click('#htmlMenuBtn');click('#saveHtmlBtn')
  for _ in range(100):
   independent_files=list(t.glob('*.html'))
   if independent_files:break
   time.sleep(.1)
  assert independent_files,'No independent round HTML export'
  call('/url',{'url':independent_files[0].as_uri()});wait('return typeof tasks!=="undefined" && tasks.length>0')
  check('independent rounds persist in exported standalone HTML',js('return structuredClone(tasks)')==independent_saved)
  call('/url',{'url':base});wait("return document.querySelector('#projectSelect').options.length>0")
  independent_files[0].unlink()
  js("tasks=arguments[0];undoStack.length=0;redoStack.length=0;store.setItem(CACHE,JSON.stringify(tasks));activeMilestone=null;drawerTaskId=null;chosen=null;render();updateHistoryButtons()",independent_before)
  # Reproduce the reported standard premium-task workflow and exact button placement.
  add_visibility_before=js('return structuredClone(tasks)')
  js("tasks.find(t=>t.id==='T05').done=false;showTask('T05')")
  check('single-round premium task has no redundant first-round badge',js("return !document.querySelector('[data-round-task]')&&!document.querySelector('.round-variants')"))
  check('round-add button is aligned to the right of the date range',js("const d=document.querySelector('.round-dates').getBoundingClientRect(),b=document.querySelector('#addRound').getBoundingClientRect(),p=document.querySelector('.round-schedule').getBoundingClientRect();return b.left>=d.right-1&&Math.abs((b.top+b.bottom-d.top-d.bottom)/2)<2&&b.right<=p.right+1"))
  click('#addRound')
  check('incomplete premium-task add button opens form with visible explanation',js("return !document.querySelector('#addRound').disabled&&!document.querySelector('#roundForm').hidden&&document.querySelector('#roundError').textContent.includes('완료')&&document.querySelector('#roundForm button[type=submit]').disabled"))
  screenshot('round-date-inline-incomplete.png');click('#cancelRound');check('cancel closes date-adjacent round form',js("return document.querySelector('#roundForm').hidden"))
  click('#drawerComplete');click('#addRound');js("document.querySelector('#roundStart').value=dateAt(BASE+90);document.querySelector('#roundEnd').value=dateAt(BASE+90)");click('#roundForm button[type=submit]')
  visibility_second=js("return roundFamily(tasks.find(t=>t.id==='T05')).at(-1).id")
  check('premium task can actually add a second round after completion',js("return roundFamily(tasks.find(t=>t.id==='T05')).length===2&&tasks.find(t=>t.id===arguments[0]).branchNo===2",visibility_second))
  check('round selectors appear inside schedule only after another round exists',js("return document.querySelectorAll('.round-schedule [data-round-task]').length===2&&!!document.querySelector('.round-schedule #deleteRound')&&!document.querySelector('.round-schedules [data-round-task]')"))
  screenshot('round-date-inline-two-rounds.png')
  click('[data-round-task="T05"]');click('#addRound');check('older round click responds with latest-round guidance',js("return !document.querySelector('#roundForm').hidden&&document.querySelector('#roundError').textContent.includes('마지막 차수')&&document.querySelector('#roundForm button[type=submit]').disabled"))
  js("showTask(arguments[0])",visibility_second);click('#drawerComplete');click('#addRound');check('completing second round enables third-round submission',js("return !document.querySelector('#roundForm').hidden&&!document.querySelector('#roundForm button[type=submit]').disabled"))
  js("tasks.find(t=>t.id===arguments[0]).notApplicable=true;showTask(arguments[0])",visibility_second);click('#addRound');check('excluded round opens form with restriction explanation',js("return !document.querySelector('#roundForm').hidden&&document.querySelector('#roundError').textContent.includes('해당없음')&&document.querySelector('#roundForm button[type=submit]').disabled"))
  js("showTask('T01')");click('#addRound');check('base review restriction has visible feedback instead of a silent click',js("return !document.querySelector('#roundForm').hidden&&document.querySelector('#roundError').textContent.includes('추가 대상')"))
  js("tasks=arguments[0];undoStack.length=0;redoStack.length=0;store.setItem(CACHE,JSON.stringify(tasks));closeTaskDrawer();updateHistoryButtons()",add_visibility_before)
  # Added rounds can be removed without deleting their base task or other rounds.
  rounds_before=js('return structuredClone(tasks)')
  js("const root={id:'T98001',name:'차수 검수',dept:'검수',type:'build',customTask:true,start:BASE+90,end:BASE+91,deps:[],done:true,events:[{id:'base-note',note:'1차 보존 메모',createdAt:'2026-10-20T00:00:00Z'}]},child={id:'T98002',name:'차수 후행 검수',dept:'검수',type:'build',customTask:true,start:BASE+91,end:BASE+92,deps:['T98001'],done:false,events:[]};tasks=normalizeTasks([...tasks,root,child]);showTask(root.id)")
  check('round controls are compact and base round has no delete action',js("return !!document.querySelector('.round-date-line #addRound')&&!document.querySelector('#deleteRound')&&!!document.querySelector('.round-schedule #addRound')"))
  click('#addRound');screenshot('round-add-form.png');click('#cancelRound');check('cancel hides new round form',js("return document.querySelector('#roundForm').hidden&&document.querySelector('#addRound').getAttribute('aria-expanded')==='false'"))
  click('#addRound');js("document.querySelector('#roundStart').value=dateAt(BASE+100);document.querySelector('#roundEnd').value=dateAt(BASE+100)");click('#roundForm button[type=submit]')
  second=js("return roundFamily(tasks.find(t=>t.id==='T98001')).at(-1).id")
  check('new round created with delete action and selected tab',js("return roundFamily(tasks.find(t=>t.id==='T98001')).length===2&&!!document.querySelector('#deleteRound')&&document.querySelector('[data-round-task=\"'+arguments[0]+'\"]').getAttribute('aria-pressed')==='true'&&Math.abs(document.querySelectorAll('[data-round-task]')[0].getBoundingClientRect().top-document.querySelectorAll('[data-round-task]')[1].getBoundingClientRect().top)<1",second))
  js("document.querySelector('#memoBody').value='2차 복구 메모'");click('#eventSave');click('#drawerComplete');click('#addRound');js("document.querySelector('#roundStart').value=dateAt(BASE+110);document.querySelector('#roundEnd').value=dateAt(BASE+110)");click('#roundForm button[type=submit]')
  third=js("return roundFamily(tasks.find(t=>t.id==='T98001')).at(-1).id")
  js("const child=tasks.find(t=>t.id==='T98002');child.start=Math.max(...roundFamily(tasks.find(t=>t.id==='T98001')).map(t=>t.end));child.end=child.start+1;child.deps=['T98001',arguments[0]];child.dependencyKinds={'T98001':'FF',[arguments[0]]:'FS'};showTask(arguments[0])",second)
  round_snapshot=js('return JSON.stringify(tasks)');round_history=js('return undoStack.length');round_dates=js("return tasks.filter(t=>t.id!==arguments[0]).map(t=>[t.id,t.start,t.end,t.done])",second)
  click('#deleteRound');call('/alert/dismiss',{})
  check('cancel round deletion preserves data and undo history',js('return JSON.stringify(tasks)')==round_snapshot and js('return undoStack.length')==round_history)
  check('base round and unsafe dependency deletion are protected',js("const before=JSON.stringify(tasks);let baseBlocked=false,cycleBlocked=false;try{removeRound(tasks,'T98001')}catch(e){baseBlocked=true}const invalid=structuredClone(tasks);invalid.find(t=>t.id==='T98001').deps=[arguments[0]];try{removeRound(invalid,arguments[0])}catch(e){cycleBlocked=true}return baseBlocked&&cycleBlocked&&JSON.stringify(tasks)===before",second))
  check('deleting standard latest round restores previous required round',js("const original=structuredClone(tasks),root=original.find(t=>t.id==='T08'),extra={...structuredClone(root),id:'T98999',roundRootId:root.id,sourceId:root.sourceId||root.id,branchNo:2,name:root.name+' [2차]',start:BASE+120,end:BASE+121,done:false};original.push(extra);const before=JSON.stringify(original),result=removeRound(original,extra.id);return requiredFor('m3',original).some(t=>t.id===extra.id)&&requiredFor('m3',result.tasks).some(t=>t.id===root.id)&&JSON.stringify(original)===before"))
  click('#deleteRound');call('/alert/accept',{})
  check('middle round deletion keeps other round numbers and base memo',js("const family=roundFamily(tasks.find(t=>t.id==='T98001'));return family.map(t=>t.branchNo||1).join(',')==='1,3'&&!tasks.some(t=>t.id===arguments[0])&&family[0].events.some(e=>e.id==='base-note')",second))
  check('linked dependencies merge safely and preserve strongest relation',js("const t=tasks.find(t=>t.id==='T98002');return t.deps.join(',')==='T98001'&&t.dependencyKinds.T98001==='FS'&&!(arguments[0] in t.dependencyKinds)",second))
  check('round deletion preserves other schedules and completion states',js("return tasks.map(t=>[t.id,t.start,t.end,t.done])")==round_dates)
  check('round deletion is one undo action',js('return undoStack.length')==round_history+1)
  click('#undoBtn');check('undo restores deleted round memos and dependencies',js('return JSON.stringify(tasks)')==round_snapshot)
  click('#redoBtn');check('redo removes round again',js('return !tasks.some(t=>t.id===arguments[0])',second))
  js('showTask(arguments[0])',third);screenshot('round-delete-toolbar.png');click('#deleteRound');call('/alert/accept',{})
  check('deleting latest round returns to base and enables adding again',js("return roundFamily(tasks.find(t=>t.id==='T98001')).length===1&&!!document.querySelector('#addRound')&&!document.querySelector('#deleteRound')"))
  js('closeTaskDrawer()');click('#projectSave');wait("return document.querySelector('#projectStatus').textContent.includes('서버 저장 완료')");round_saved=js('return structuredClone(tasks)');call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0")
  check('deleted rounds and repaired dependencies persist after reload',js('return structuredClone(tasks)')==round_saved)
  js("tasks=arguments[0];undoStack.length=0;redoStack.length=0;store.setItem(CACHE,JSON.stringify(tasks));activeMilestone=null;drawerTaskId=null;chosen=null;render();updateHistoryButtons()",rounds_before)
  # Actual disclosure controls: one visible relation and one newest mixed memo.
  js("window.qaSaved={tasks:structuredClone(tasks),history:undoStack.length};const task=(id,deps,start)=>({id,name:id+' 검수업무',dept:'검수',type:'build',customTask:true,start,end:start+1,deps,events:[]});tasks=normalizeTasks([...tasks,task('T99001',[],BASE+99),task('T99002',[],BASE+99),task('T99003',['T99001','T99002'],BASE+100),task('T99004',['T99003'],BASE+101),task('T99005',['T99003'],BASE+101)]);const t=tasks.find(t=>t.id==='T99003');t.events=[{id:'older',note:'과거 사용자 메모',createdAt:'2026-10-20T00:00:00Z'},{id:'newest',note:'최근 사용자 메모',createdAt:'2026-10-23T00:00:00Z'}];t.scheduleChanges=[{id:'sys',text:'과거 시스템 메모',time:'2026-10-22T00:00:00Z',acknowledged:false}];showTask(t.id)")
  check('one predecessor and successor visible initially',js("return ['before','after'].every(k=>{const g=document.querySelector('[data-relation='+k+']');return g.querySelectorAll(':scope > .relation-card').length===1&&g.querySelector('.relation-more')&&!g.querySelector('.relation-more').open})"))
  click('[data-relation="before"] .relation-more > summary');check('remaining predecessor expands',js("return document.querySelector('[data-relation=before] .relation-more').open"))
  check('newest mixed memo visible without deleting history',js("const e=document.querySelector('.memo-entries');return e.querySelectorAll(':scope > .memo-entry').length===1&&e.querySelector(':scope > .memo-entry').textContent.includes('최근 사용자 메모')&&e.querySelectorAll('.memo-history .memo-entry').length===2&&!e.querySelector('.memo-history').open"))
  check('bar tooltip contains only newest memo',js("const text=document.querySelector('#chart .bar[data-id=T99003]').title;return text.includes('최근 사용자 메모')&&!text.includes('과거 사용자 메모')&&!text.includes('과거 시스템 메모')"))
  click('.memo-history > summary');click('[data-edit-memo="older"]');js("document.querySelector('#memoBody').value='수정한 과거 메모'");click('#eventSave')
  check('older user memo remains editable and visible after save',js("return document.querySelector('.memo-history').open&&tasks.find(t=>t.id==='T99003').events.find(e=>e.id==='older').note==='수정한 과거 메모'"))
  js("showTask('T99001')");check('empty predecessor list says none',js("return document.querySelector('[data-relation=before] .drawer-empty').textContent==='없음'"))
  js("showTask('T99004')");check('single relation has no unnecessary expander and empty successors say none',js("return !document.querySelector('[data-relation=before] .relation-more')&&document.querySelector('[data-relation=after] .drawer-empty').textContent==='없음'"))
  js("tasks=qaSaved.tasks;undoStack.length=qaSaved.history;redoStack.length=0;store.setItem(CACHE,JSON.stringify(tasks));closeTaskDrawer();updateHistoryButtons();delete window.qaSaved")
  # Migrate only identifiable legacy sale-system notes; preserve task/user notes.
  migration=js("""const legacy=structuredClone(tasks),owner=legacy.find(t=>t.id==='T01'),prep=legacy.find(t=>t.id==='T33');delete owner.saleDetails;owner.saleDate=dateAt(BASE+105);owner.saleConfirmed=true;owner.events=[{id:'legacy-user',note:'상품안 사용자 메모'}];owner.scheduleChanges=[{id:'sale-legacy',text:prep.name+' 일정이 변경되었습니다.',time:'2026-10-23T00:00:00Z',acknowledged:true},{id:'sale-explicit',text:'옛 업무 일정이 변경되어 판매개시일이 변경되었습니다.',time:'2026-10-23T00:00:00Z',acknowledged:false},{id:'task-legacy',text:'상품안 검토 자체의 기록',time:'2026-10-23T00:00:00Z',acknowledged:false}];const normalized=normalizeTasks(legacy),root=normalized.find(t=>t.id==='T01'),sale=meetingRecord('ready',normalized);return {taskNotes:root.scheduleChanges.map(n=>n.id),saleNotes:sale.scheduleChanges,events:root.events,saleDate:sale.saleDate,confirmed:sale.saleConfirmed,idempotent:JSON.stringify(normalizeTasks(normalized))===JSON.stringify(normalized),legacyRemoved:!('saleDate' in root)}""")
  check('legacy sale notes separated without losing task notes',migration['taskNotes']==['task-legacy'] and [n['id'] for n in migration['saleNotes']]==['sale-legacy','sale-explicit'])
  check('migration preserves user notes dates confirmation and acknowledgement',migration['events'][0]['note']=='상품안 사용자 메모' and migration['saleDate'] and migration['confirmed'] and migration['saleNotes'][0]['acknowledged'] and migration['legacyRemoved'])
  check('sale migration is idempotent',migration['idempotent'])
  js("tasks=normalizeTasks(tasks);const prep=tasks.find(t=>t.id==='T33');prep.name='검수용 판매준비';prep.start=BASE+100;prep.end=BASE+101;prep.deps=[];meetingRecord('ready').saleDate=dateAt(BASE+105);meetingRecord('ready').saleConfirmed=false;store.setItem(CACHE,JSON.stringify(tasks));render()")
  review_before=js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")
  js("quickDuration({dataset:{id:'T33'},value:'2'})")
  check('prep change writes only to sale memo collection',js("return meetingRecord('ready').scheduleChanges.some(n=>n.text.includes('검수용 판매준비'))") and js("return JSON.stringify(tasks.find(t=>t.id==='T01').scheduleChanges)")==review_before)
  js("showTask('T01')")
  check('task drawer hides sale-system notes',js("return !document.querySelector('.memo-entries').textContent.includes('검수용 판매준비')"))
  js('closeTaskDrawer()');click('#readyCard')
  check('sale detail displays sale-system notes',js("return document.querySelector('.memo-entries').textContent.includes('검수용 판매준비')"))
  js("document.querySelector('#memoBody').value='판매개시 전용 사용자 메모'");click('#eventSave')
  check('sale user memo stays separate from task user memos',js("return meetingRecord('ready').events.some(e=>e.note==='판매개시 전용 사용자 메모')&&!tasks.find(t=>t.id==='T01').events.some(e=>e.note==='판매개시 전용 사용자 메모')"))
  check('sale-system memos have no delete button',js("return !document.querySelector('[data-delete-memo][data-memo-kind=\"system\"]')&&meetingRecord('ready').scheduleChanges.some(n=>n.text.includes('검수용 판매준비'))"))
  js('closeBreakdown()')
  # Open an actual task via a chart bar; snapshot state only for assertions.
  before=js('return structuredClone(tasks)');tid=before[0]['id']
  js("showTask(arguments[0])",tid);click('#drawerComplete');check('complete task',js('return tasks.find(t=>t.id===arguments[0]).done',tid))
  click('#undoBtn');check('undo completion',js('return !tasks.find(t=>t.id===arguments[0]).done',tid));click('#redoBtn');check('redo completion',js('return tasks.find(t=>t.id===arguments[0]).done',tid));click('#undoBtn')
  js('closeTaskDrawer()');click('#exclusionEditBtn');click('#addTaskBtn');js("document.querySelector('#newName').value='QA <script> & 업무';document.querySelector('#newDept').value='__custom__';document.querySelector('#newDept').dispatchEvent(new Event('change'));document.querySelector('#newDeptCustom').value='검수부서'")
  required_before=js("return ['m2','m3','ready'].map(k=>[requiredFor(k).map(t=>t.id),meetingDateValue(k)])")
  js("document.querySelector('#newType').value='review';document.querySelector('#newDuration').value='200';document.querySelector('#newDuration').dispatchEvent(new Event('change'))")
  click('#addTaskForm button[type=submit]')
  try:call('/alert/accept',{})
  except RuntimeError as error:
   if 'no such alert' not in str(error):raise
  check('add custom task',js("return tasks.some(t=>t.name==='QA <script> & 업무')"))
  check('custom work does not change required tasks or meeting dates',js("return ['m2','m3','ready'].map(k=>[requiredFor(k).map(t=>t.id),meetingDateValue(k)])")==required_before)
  added=js("return structuredClone(tasks.find(t=>t.name==='QA <script> & 업무'))");check('custom name displayed as text',js("return Array.from(document.querySelectorAll('#chart .bar-text')).some(e=>e.textContent.includes('QA <script> & 업무') && !e.querySelector('script'))"))
  js('showTask(arguments[0])',added['id']);click('#drawerEdit');js("const e=document.querySelector('#inlineDuration');e.value='4';e.dispatchEvent(new Event('input'))")
  click('#inlineEditor button[type=submit]');check('edit task duration',js('return tasks.find(t=>t.id===arguments[0]).end-tasks.find(t=>t.id===arguments[0]).start===4',added['id']))
  # A same-ID user memo can be deleted without touching the system record.
  js("const t=tasks.find(t=>t.id===arguments[0]);t.events.push({id:'qa-collision',note:'사용자 보존',createdAt:new Date().toISOString()});t.scheduleChanges=[{id:'qa-collision',text:'시스템 보존 검수',time:new Date().toISOString(),acknowledged:true}];showTask(t.id)",added['id'])
  check('system memo cannot be edited or deleted',js("return !document.querySelector('.memo-entries > .memo-entry [data-delete-memo]')&&!document.querySelector('.memo-entries > .memo-entry [data-edit-memo]')"))
  check('latest memo visible and older memos collapsed',js("return document.querySelectorAll('.memo-entries > .memo-entry').length===1&&document.querySelector('.memo-history')&&!document.querySelector('.memo-history').open"))
  click('.memo-history > summary');click('[data-delete-memo="qa-collision"][data-memo-kind="user"]')
  check('user memo deletion preserves same-ID system memo',js("const t=tasks.find(t=>t.id===arguments[0]);return t.scheduleChanges.some(m=>m.id==='qa-collision')&&!t.events.some(m=>m.id==='qa-collision')",added['id']))
  click('#undoBtn');check('undo user memo deletion',js("return tasks.find(t=>t.id===arguments[0]).events.some(m=>m.id==='qa-collision')",added['id']))
  click('#redoBtn');check('redo user memo deletion preserves system memo',js("const t=tasks.find(t=>t.id===arguments[0]);return !t.events.some(m=>m.id==='qa-collision')&&t.scheduleChanges.some(m=>m.id==='qa-collision')",added['id']))
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
