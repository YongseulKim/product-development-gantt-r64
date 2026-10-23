"""Real Chromium/WebDriver checks, with temporary server DB and browser profile."""
import base64,importlib.util,json,os,socket,subprocess,tempfile,threading,time,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from browser_environment import browser_environment
R=Path(__file__).resolve().parents[1];E=R/'docs/evidence/revisions';E.mkdir(exist_ok=True)
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
  selected=set(os.environ.get('REV_ONLY','').split(','))-{''}
  results=json.loads((E/'results.json').read_text()) if selected and (E/'results.json').exists() else []
  def run(id,fn,limit=''):
   if selected and id not in selected:return
   results[:]=[x for x in results if x['id']!=id]
   start=time.time()
   try:
    detail=fn();status='부분 통과' if limit else '통과'
   except Exception as error:
    status='실패';detail=str(error)
    try:screenshot(id+'-failure.png');(E/(id+'-dom.html')).write_text(js('return document.documentElement.outerHTML'));(E/(id+'-state.json')).write_text(json.dumps(js('return tasks'),ensure_ascii=False,indent=2))
    except Exception:pass
    try:call('/alert/dismiss',{})
    except Exception:pass
   results.append({'id':id,'status':status,'detail':detail,'remaining':limit,'seconds':round(time.time()-start,1)})
   (E/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(id,status,str(detail)[:350],flush=True)
  def expect(ok,message):
   if not ok:raise AssertionError(message)
  call('/url',{'url':base});wait("return document.querySelector('#projectSelect').options.length>0")
  canonical=js('return structuredClone(tasks)');process=js('return PROCESS_VERSION');baseOffset=js('return BASE')
  # Base tasks are retained for fixed meeting/summary IDs. Synthetic test tasks use IDs >= 900.
  def task(n,name,start,end,deps=[],type='build',done=False,notes=[]):
   return {'id':'T'+str(n),'name':name,'dept':'검수부서','type':type,'start':baseOffset+start,'end':baseOffset+end,'deps':deps,'customTask':True,'processVersion':process,'done':done,'events':[{'id':'e'+str(i),'note':note,'date':'','name':'','createdAt':'2026-10-20T00:00:00Z'} for i,note in enumerate(notes)]}
  def load(extra=[],kickoff='2026-09-01',holidays=''):
   js("""tasks=normalizeTasks(arguments[0]);kickoffDate=arguments[1];kickoffAuto=false;holidayText=arguments[2];refreshHolidays(holidayText);respectMilestones=false;undoStack.length=0;redoStack.length=0;selectedTasks.clear();activeMilestone=null;drawerTaskId=null;chosen=null;editingId=null;draft=null;exclusionEdit=false;$('holidayInput').value=holidayText;store.setItem(CACHE,JSON.stringify(tasks));render();updateHistoryButtons();""",canonical+extra,kickoff,holidays)
  def states():return js('return structuredClone(tasks)')
  def get(id):
   value=js('return structuredClone(tasks.find(t=>t.id===arguments[0]))',id);value['start']-=baseOffset;value['end']-=baseOffset;return value
  def memo(id,text):
   js("showTask(arguments[0]);$('memoBody').value=arguments[1];$('memoForm').requestSubmit()",id,text)
  def edit(id,start,duration):
   js("openInline(arguments[0]);$('inlineStart').value=dateAt(arguments[1]);$('inlineDuration').value=String(arguments[2]);$('inlineEditor').requestSubmit()",id,baseOffset+start,duration)
   error=js("return $('inlineError')?.textContent||''");expect(not error,error)
  def complete(id):js("showTask(arguments[0]);$('drawerComplete').click()",id)
  def offset(date):return js('return offsetForDate(arguments[0])-BASE',date)
  def save():
   js("closeTaskDrawer();$('projectSave').click()")
   wait("return !$('projectSave').disabled && $('projectStatus').textContent.includes('서버 저장 완료')")
  def reload():call('/refresh',{});wait("return document.querySelector('#projectSelect').options.length>0")
  def save_reload():
   save();before=states();reload();expect(states()==before,'저장/재조회 데이터 불일치');return before
  groups=['26.9월 예시상품A','26.예시개정B','26.11월 예시상품C','26.11월 예시상품D','26.11월 예시상품E','26.11월 예시상품F'];projects={}
  def rev01():
   for name in groups:
    state={'tasks':canonical+[task(900,'레이아웃',0,3)],'kickoffDate':'2026-09-01','holidayText':'','respectMilestones':False,'name':'[검수] '+name,'notes':[],'initialMessages':[]}
    rec=http(base+'/api/projects',{'state':state});projects[name]=rec
   direct=projects[groups[3]];call('/url',{'url':base+'/?project='+direct['id']});wait("return document.querySelector('#projectSelect').options.length===7")
   edit('T900',1,4);complete('T900');memo('T900','개정별 독립 변경');save_reload()
   for name in [groups[5],groups[1]]:
    rec=http(base+'/api/projects/'+projects[name]['id']);expect(rec['state']['tasks'][-1]['end']==baseOffset+3 and not rec['state']['tasks'][-1].get('done'),'타 개정 오염')
   return '6개 서버 상품 생성, 한 상품 날짜·완료·메모 저장/재로드, 타 개정 독립 확인(API)'
  run('REV-01',rev01)
  def rev02():
   load([task(900,'다이렉트 의견',0,2),task(901,'예시상품E 의견',0,2)]);memo('T900','공동 실무협의 2026-10-02 / 의견 2026-10-13');memo('T901','공동 회의 SRC-38');complete('T901');save_reload()
   expect(not get('T900')['done'] and get('T901')['done'],'의견 상태 혼입');return '공동 출처 메모와 독립 의견 완료 보존. 개정 간 분리는 REV-01로 확인'
  run('REV-02',rev02,'공동 회의 동기화 전용 모델 없음. 각각 메모로 기록')
  # Date conflicts are an input-review result rather than a fabricated browser pass.
  results.append({'id':'REV-03','status':'입력 확인 필요','detail':'SRC-12 메타 2026-09-08 / 본문 9/2(화), 실제 2026-09-02는 수요일. SRC-06~08은 메타 10/12 / 본문 9/23. 채택할 실제 일정은 담당 확인 필요. 브라우저에 임의 확정 등록하지 않음.','remaining':'원본 날짜 의미 확인'})
  def rev04():
   load([task(900,'서면 실무협의',0,1,done=True),task(901,'부서 A 검토의견',0,3),task(902,'부서 B 검토의견',0,3)])
   memo('T900','서면 개최 공문 발신 / SRC-01');complete('T901');save_reload();expect(get('T900')['done'] and get('T901')['done'] and not get('T902')['done'],'서면발신/회신 상태 혼입');return '서면 공문·부서 A/B 개별 업무 및 상태 저장 확인'
  run('REV-04',rev04,'실제 부서 하위업무 미수집. 부모/하위업무·담당자 전용 필드 없음')
  def rev05():
   load([task(900,'위험률',0,6)]);memo('T900','초안 완료 / 계리법인검증 완료 / 계리지원 검증 진행 중');save_reload();expect(not get('T900')['done'],'부분 완료를 전체 완료로 오판');complete('T900');save_reload();expect(get('T900')['done'] and len(get('T900')['events'])==1,'최종 완료/이력 유실');return '단계 메모와 미완료→최종 완료, 저장/재로드 통과'
  run('REV-05',rev05)
  def chain(end=5):return [task(900,'수익성분석',0,end),task(901,'후행검토',end,end+2,['T900']),task(902,'독립업무',0,2)]
  def rev06():
   load(chain());d1=offset('2026-09-17')+1;d2=offset('2026-09-23')+1;d3=offset('2026-09-30')+1
   edit('T900',0,d1);memo('T900','9/17 → 9/23 로직 구현 지연');edit('T900',0,d2);memo('T900','9/23 → 9/30 추가 구현 및 작업량 산정 미비');before=states();edit('T900',0,d3)
   expect(get('T901')['start']==d3 and get('T902')['start']==0,'후행/독립 날짜 오류');js('undo()');expect(states()==before,'취소 데이터 불일치');js('redo()');expect(get('T900')['end']==d3,'재실행 실패');save_reload();return '9/17→9/23→9/30, 원인 메모 2개·후행 간격·취소/재실행 및 저장 통과'
  run('REV-06',rev06)
  def rev07():
   extra=[task(900,'예상매출',0,3,done=True),task(901,'예상손해율',0,3,done=True),task(902,'PV테이블',0,4),task(903,'PV프로그램',0,3),task(904,'레이아웃',0,3,done=True),task(905,'수익성분석',4,6,['T900','T901','T902','T903','T904'])]
   load(extra);edit('T902',0,6);expect(get('T905')['start']==6 and get('T905')['end']==8,'복수 선행 max 전파 오류');expect(not get('T905')['done'],'미수령 오판');save_reload();return '5개 선행자료 중 PV 최장 종료 4→6, 분석 4~6→6~8 확인'
  run('REV-07',rev07,'선행 연결은 fixture로 준비. 현행 UI에 연결 편집 입력 없음')
  def meeting(kind,date,confirmed=False):
   js("activeMilestone=arguments[0];drawerTaskId=null;editingId=null;render();$('meetingDate').value=arguments[1];$('meetingDatePicker').click();[...document.querySelectorAll('#dateCalendar [data-date]')].find(b=>b.dataset.date===arguments[1]).click();$('meetingConfirmed').checked=arguments[2];$('meetingSave').click()",kind,date,confirmed)
   expect(not js("return $('meetingError')?.textContent"),js("return $('meetingError')?.textContent"))
  def rev08():
   load();js("for(const t of tasks){if(!t.meetingKind){t.start=BASE-20;t.end=BASE-19}};render()")
   meeting('m2','2026-10-02');meeting('m3','2026-10-13');expect(not js("return meetingRecord('m2').confirmedDate||meetingRecord('m3').confirmedDate"),'예정 저장이 확정됨')
   meeting('m2','2026-10-02',True);meeting('m3','2026-10-13',True);expect(js("return !!meetingRecord('m3').confirmedDate"),'확정 실패');save_reload();return '10/2·10/13 예정 저장과 확정 별도 처리 및 저장 통과'
  run('REV-08',rev08)
  def rounds(root,day):
   js('showTask(arguments[0])',root);expect(js("return !!$('addRound')"),'완료 후 차수 추가 버튼 없음');js("$('addRound').click();$('roundStart').value=arguments[0];$('roundEnd').value=arguments[0];$('roundForm').requestSubmit()",day)
   error=js("return $('roundError')?.textContent||''");expect(not error,error)
  def rev09():
   load([task(900,'수익성분석',0,3,done=True,notes=['1차 완료 기록'])]);rounds('T900','2026-10-12');family=js("return roundFamily(tasks.find(t=>t.id==='T900'))");expect(len(family)==2 and not family[-1]['done'] and get('T900')['done'],'재산출 회차/완료 오류');expect(js("return requiredFor('m2').some(t=>t.branchNo===2&&t.roundRootId==='T900')"),'최신 회차 필수 미반영');save_reload();return '실제 차수 폼으로 10/12 재산출 추가, 1차 완료 이력 및 최신 회차 필수 반영'
  run('REV-09',rev09)
  def rev10():
   load([task(900,'레이아웃',0,3,done=True),task(901,'기초서류',0,3,done=True)]);memo('T900','위원회 후 10/14 명칭 수정');rounds('T900','2026-10-14');rounds('T901','2026-10-14');save_reload();expect(len(js('return tasks.filter(t=>t.branchNo===2)'))==2,'수정 회차 누락');expect(get('T900')['done'] and get('T901')['done'],'과거 완료 유실');return '두 업무 수정 회차 미완료 및 기존 완료 보존'
  run('REV-10',rev10,'자동 재검토 승인 모델 없음. 명시적 회차와 메모로 표현')
  def rev11():
   load([task(900,'전체약관 확정',0,3),task(901,'할인조건 확정',0,3),task(902,'추가지침 개발',3,5,['T900','T901']),task(903,'오픈 전 검증',5,7,['T902'],type='prep')]);edit('T900',0,6);expect(get('T902')['start']==6 and get('T903')['start']==8,'개발 검증 전파 누락');edit('T900',0,3);expect(get('T903')['start']==8,'현행 후행 일정 유지 정책 불일치');expect(not js("return scheduleErrors(tasks.find(t=>t.id==='T903'),tasks).length"),'해소 후 일정 제약 오류');save_reload();return '확정→개발→검증 지연 전파 확인. 선행을 앞당겨도 후행은 유지하는 현행 정책 확인(자동 원복 아님)' 
  run('REV-11',rev11,'과거 판매일은 자동 조정하지 않는 현행 정책. 판매 경고의 전체 조합은 별도')
  def rev12():
   load([task(900,'검증계 반영',0,2,done=True),task(901,'후선 선오픈',2,3),task(902,'현장 오픈',3,4),task(903,'추후 반영 종형',4,5)]);memo('T901','2026-10-19 19:30~20:30');memo('T902','현장 2026-10-21');complete('T901');save_reload();expect(get('T901')['done'] and not get('T902')['done'] and not get('T903')['done'],'부분 출시 상태 혼입');return '3단계/추후 범위와 시각 메모 보존'
  run('REV-12',rev12,'시각 단위·환경별 출시 전용 모델 없음. 개별 업무와 메모 사용')
  def rev13():
   load();extra=[task(900,'레이아웃',0,offset('2026-09-28')+1,done=True),task(901,'PV테이블',0,offset('2026-10-21')+1),task(902,'기초서류',0,offset('2026-10-21')+1),task(903,'수익성분석',0,offset('2026-10-16')+1,done=True)];load(extra);memo('T901','초안 9/21 · 수정 10/6 · 전달 10/16');save_reload();expect(get('T900')['done'] and get('T903')['done'] and not get('T901')['done'] and not get('T902')['done'],'완료/진행 혼입');return '명시된 업무 상태와 PV 전달 이력 보존'
  run('REV-13',rev13)
  def rev14():
   load();end=offset('2026-10-21')+1;load(chain(end));before=states();edit('T900',0,offset('2026-10-23')+1);expect(get('T901')['start']==end+2,'PV 지연 전파 오류');js('undo()');expect(states()==before,'PV 지연 취소 복원 오류');save_reload();return '10/21→10/23(+2영업일) 영향/취소/저장 확인'
  run('REV-14',rev14)
  def rev15():
   load();extra=[task(900,'검토의견',0,offset('2026-10-20')+1),task(901,'레이아웃',0,offset('2026-10-21')+1),task(902,'기초서류',0,offset('2026-10-23')+1),task(903,'PV테이블',0,offset('2026-10-23')+1),task(904,'수익성분석',0,3,done=True)];load(extra);complete('T901');save_reload();expect(get('T901')['done'] and not get('T902')['done'] and not get('T903')['done'],'어린이 상태 혼입');return '10/20·10/21·10/23 독립 일정 및 레이아웃만 완료 확인; 개정 분리 REV-01'
  run('REV-15',rev15)
  def rev16():
   load([task(900,'어린이 수익성분석',0,3,done=True),task(901,'예시상품B 수익성분석',0,3,done=True)]);memo('T900','공유 분석자료 / 10/19 어린이 월납실적 수정');rounds('T900','2026-10-20');save_reload();expect(get('T901')['done'] and not get('T901')['events'],'공유 자료 수정 범위 혼입');return '공유 자료의 어린이 변경 메모/재검토만 추가, 예시상품B 완료 유지'
  run('REV-16',rev16,'공유 산출물 버전 연결 전용 기능 없음. 명시 업무/메모 사용')
  def rev17():
   load([task(900,'안건1 선택형할인',0,3),task(901,'안건2 계약전환',0,3),task(902,'안건3 안정화할인',0,3)]);memo('T900','시행일 2026-11-01 (달력 날짜)');memo('T901','시행일 2026-11-01');memo('T902','시행일 2026-10-01');complete('T902');save_reload();expect(not get('T900')['done'] and get('T902')['done'],'안건별 상태 혼입');expect('2026-11-01' in get('T900')['events'][0]['note'],'일요일 시행일 메모 변형');return '복수 달력 시행일 메모 보존 및 안건3만 완료 확인'
  run('REV-17',rev17,'판매개시 카드는 상품당 단일 날짜이고 휴일 선택 금지. 복수 시행일은 전용 기능 공백')
  def rev18():
   load([task(900,'안건1 기초서류',0,3),task(901,'안건2 기초서류',0,3),task(902,'설명서 확정',0,4,type='prep'),task(903,'숙려기간 확정',0,4,type='prep')]);memo('T900','9/30 수정 반영');memo('T901','현재 수정 없음 / 공람 회신 없음');memo('T902','초안 미확정');complete('T900');save_reload();expect(not get('T902')['done'] and not get('T903')['done'],'서류 일부완료를 전체완료로 오판');expect(js("return requiredFor('ready').some(t=>t.id==='T902')"),'준비업무 누락');return '안건별 자료 이력 및 미확정 준비 업무 확인'
  run('REV-18',rev18,'미확정 전용 상태 대신 메모+미완료로 표현')
  results.append({'id':'REV-19','status':'입력 검토 완료 / 기능 공백','detail':'44개 출처 색인 검토: 그룹 미지정 14개. SRC-20/33 같은 10/2 회의로 연결 가능. SRC-17/38 공동 회의 후보, SRC-44 공통 공유회는 상품 업무로 자동 등록하지 않음.','remaining':'자동 분류·공지 중복제거·공통 공지 전용 모델 없음. 수동 검토 필요'})
  def rev20():
   load([task(900,'위원회 자료X',0,3,type='review'),task(901,'자료X 후행전산',3,5,['T900'],type='prep')]);js("activeMilestone='m3';render();const e=document.querySelector('[data-required-key=\"T900\"]');$('meetingDate').value=dateAt(Math.max(...requiredFor('m3').map(t=>t.end),meetingRecord('m2').start+6)+5);const date=$('meetingDate').value;$('meetingDatePicker').click();document.querySelector('#dateCalendar [data-date=\"'+date+'\"]').click();e.checked=true;e.dispatchEvent(new Event('change'));$('meetingSave').click()")
   expect(not get('T900')['notApplicable'] and 'T900' in get('T901')['deps'],'회의제외가 실제 업무 손상');expect(js("return !requiredFor('m3').some(t=>t.id==='T900')"),'회의제외 미반영')
   js("setNotApplicable('T900',true)");expect(get('T900')['notApplicable'],'업무제외 실패');js("setNotApplicable('T900',false)");expect(not get('T900')['notApplicable'] and 'T900' in get('T901')['deps'],'복원 오류');save_reload();return '실제 필수조건 체크, 업무 제외/복원 및 저장 후 관계 보존'
  run('REV-20',rev20)
  def rev21():
   load([task(900,'충돌 검수',0,3)]);save();first=http(base+'/api/projects/'+js('return window.GANTT_SERVER.id'));newtab=call('/window/new',{'type':'tab'})['handle'];oldhandle=http(endpoint+'/window')['value'];call('/window',{'handle':newtab});call('/url',{'url':base+'/?project='+first['id']});wait("return document.querySelector('#projectSelect').options.length>0")
   # Preserve B's stale page, change A via actual UI in the original tab.
   call('/window',{'handle':oldhandle});memo('T900','A 먼저 저장');save();a=http(base+'/api/projects/'+first['id']);call('/window',{'handle':newtab});memo('T900','B 충돌 보관');js("closeTaskDrawer();$('projectSave').click()")
   for _ in range(60):
    try:
     alert=http(endpoint+'/alert/text')['value'];break
    except Exception:time.sleep(.2)
   expect('다른 사용자가 먼저 저장' in alert,'충돌 안내 없음');call('/alert/accept',{});expect(http(base+'/api/projects/'+first['id'])['version']==a['version'],'충돌 시 덮어씀')
   js("$('htmlMenuBtn').click();$('saveHtmlBtn').click()")
   files=[]
   for _ in range(100):
    files=list(t.glob('*.html'))
    if files:break
    time.sleep(.1)
   expect(bool(files),'충돌 HTML 다운로드 실패');download=files[-1];savedB=states()
   call('/url',{'url':download.as_uri()});expect(states()==savedB,'충돌 HTML 재실행 데이터 불일치')
   call('/window',{'handle':oldhandle});call('/url',{'url':base+'/?project='+first['id']});wait("return document.querySelector('#projectSelect').options.length>0");count=len(http(base+'/api/projects')['projects'])
   el=call('/element',{'using':'css selector','value':'#loadHtmlInput'})['element-6066-11e4-a52e-4f735466cecf'];call('/element/'+el+'/value',{'text':str(download),'value':list(str(download))});wait('return window.GANTT_SERVER.id!=='+json.dumps(first['id']))
   expect(len(http(base+'/api/projects')['projects'])==count+1 and states()==savedB,'충돌 HTML 새상품 이관 오류');expect(http(base+'/api/projects/'+first['id'])['version']==a['version'],'기존상품 손상');return '실제 2개 탭 동시편집 충돌, B HTML 보관·재실행·신규상품 이관, A 보존'
  run('REV-21',rev21)
  def drag(selector,dx,dy=0):
   el=call('/element',{'using':'css selector','value':selector});key=el['element-6066-11e4-a52e-4f735466cecf'];js('document.querySelector(arguments[0]).scrollIntoView({block:"center",inline:"center"});window.qaPointerLog=[];if(!window.qaPointerBound){document.addEventListener("pointerdown",e=>window.qaPointerLog.push({type:e.type,target:e.target.outerHTML.slice(0,300),x:e.clientX,y:e.clientY}),true);window.qaPointerBound=true}',selector)
   call('/actions',{'actions':[{'type':'pointer','id':'mouse','parameters':{'pointerType':'mouse'},'actions':[{'type':'pointerMove','duration':100,'origin':{'element-6066-11e4-a52e-4f735466cecf':key},'x':0,'y':0},{'type':'pointerDown','button':0},{'type':'pointerMove','duration':700,'origin':'pointer','x':round(dx),'y':dy},{'type':'pointerUp','button':0}]}]})
   (E/'pointer-last.json').write_text(json.dumps(js('return window.qaPointerLog'),ensure_ascii=False,indent=2))
  def rev22():
   load([task(900,'PC 이동',0,4),task(901,'PC 후행',4,6,['T900']),task(902,'PC 독립',0,4)],kickoff='2026-10-23')
   before=states();edit('T900',2,4);expected=states();js('undo();closeTaskDrawer()');expect(states()==before,'상세편집 취소 오류')
   # At Fri Oct23, +2 business days is Tue Oct27: four calendar cells.
   cell=js('return cell');drag('#chart .bar[data-id="T900"]',4*cell);expect([(get(x)['start'],get(x)['end']) for x in ['T900','T901']]==[(x['start']-baseOffset,x['end']-baseOffset) for x in expected if x['id'] in ['T900','T901']],'마우스 이동과 상세편집 결과 불일치')
   js('undo()');expect(states()==before,'드래그 취소 오류')
   drag('#chart .bar[data-id="T900"] .resize-handle[data-mode="resize-end"]',cell);expect(get('T900')['end']==5,'오른쪽 기간조절 실패');js('undo()')
   drag('#chart .bar[data-id="T900"] .resize-handle[data-mode="resize-start"]',3*cell);expect(get('T900')['start']==1 and get('T900')['end']==4,'왼쪽 기간조절 실패: '+str(get('T900')));js('undo()')
   js("selectedTasks.add('T900');selectedTasks.add('T901');refreshMultiSelection()")
   drag('#chart .bar[data-id="T900"]',4*cell);expect(get('T900')['start']==2 and get('T901')['start']==6,'다중선택 중복 전파');js('undo();selectedTasks.clear()')
   for width,height in [(1280,800),(1920,1080)]:
    call('/window/rect',{'width':width,'height':height});js("$('zoomIn').click();$('scroll').scrollLeft=0");c=js('return cell');drag('#chart .bar[data-id="T900"]',4*c);expect(get('T900')['start']==2,'줌/해상도 이동 오류');js('undo()');screenshot('desktop-'+str(width)+'.png')
   # Actual keyboard chord rather than invoking the undo function.
   drag('#chart .bar[data-id="T900"]',4*js('return cell'))
   def keys(letter):call('/actions',{'actions':[{'type':'key','id':'keyboard','actions':[{'type':'keyDown','value':'\ue009'},{'type':'keyDown','value':letter},{'type':'keyUp','value':letter},{'type':'keyUp','value':'\ue009'}]}]})
   keys('z');expect(get('T900')['start']==0,'Ctrl+Z 실패');keys('y');expect(get('T900')['start']==2,'Ctrl+Y 실패')
   stable=states();reference=js('return referenceDate');drag('#axis .today-handle',js('return cell'));expect(js('return referenceDate')!=reference,'기준일 헤더 드래그 실패');expect(states()==stable,'기준일 드래그가 업무일정 변경')
   js("openInline('T900');$('inlineStart').value=dateAt(BASE+366);$('inlineDuration').value='4';$('inlineEditor').requestSubmit()");expect(bool(js("return $('inlineError').textContent")) and states()==stable,'지원 범위 밖 입력이 일정 손상');js('cancelInline();closeTaskDrawer()');screenshot('desktop-final.png');return '실제 WebDriver 마우스 드래그/양끝 조절/다중선택/줌/1280·1920px/Ctrl+Z·Y 확인'
  run('REV-22',rev22,'다중선택 목록은 fixture로 지정. 실제 Ctrl+클릭 선택 절차·지원범위 밖 마우스 드래그는 미검수(입력 거부만 확인)')
  logs=call('/log',{'type':'browser'});(E/'console.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2))
 finally:
  (E/'results.json').write_text(json.dumps(sorted({x['id']:x for x in locals().get('results',[])}.values(),key=lambda x:x['id']),ensure_ascii=False,indent=2))
  if sid:
   try:
    req=urllib.request.Request(wd+'/session/'+sid,method='DELETE');urllib.request.urlopen(req,timeout=10).close()
   except Exception:pass
  driver.terminate();driver.wait(timeout=10);log.close();server.shutdown();server.server_close()
