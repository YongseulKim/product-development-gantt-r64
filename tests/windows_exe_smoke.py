"""Run the actual packaged executable with installed Python removed from PATH."""
from pathlib import Path
import json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1];exe=ROOT/'dist/GanttServerManager.exe';report=ROOT/'dist/exe-self-test.json'
with tempfile.TemporaryDirectory(prefix='gantt-exe-') as temp:
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
 env['PATH']=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32')
 command=[str(exe),'--self-test','--data-dir',temp,'--test-report',str(report)]
 process=subprocess.Popen(command,env=env,cwd=temp)
 try:code=process.wait(timeout=150)
 except subprocess.TimeoutExpired:
  subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL);raise
 if code:
  for path in [exe.parent/'manager-startup-error.log',*Path(temp).glob('logs/*.jsonl')]:
   if path.exists():print(path.read_text(encoding='utf-8'))
  if report.exists():print(report.read_text(encoding='utf-8'))
  raise SystemExit(code)
 data=json.loads(report.read_text(encoding='utf-8'));assert data['success'] and data['frozen'] and data['passed']>=12,data
 print(json.dumps({'success':True,'frozen':True,'passed':data['passed']},ensure_ascii=False))
