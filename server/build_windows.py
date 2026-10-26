"""Run on Windows. Only public starter assets are bundled; never data/ or backups."""
from pathlib import Path
import os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
if sys.platform!='win32':raise SystemExit('Windows 환경에서 빌드해야 합니다.')
stage=ROOT/'build/windows-assets';stage.mkdir(parents=True,exist_ok=True)
shutil.copy2(ROOT/'server/server.py',stage/'backend_server.py')
from PIL import Image,ImageDraw
image=Image.new('RGBA',(256,256),'#183769');draw=ImageDraw.Draw(image)
for y,a,b in [(52,35,155),(112,78,222),(172,43,190)]:draw.rounded_rectangle((a,y,b,y+30),radius=8,fill='white')
image.save(stage/'gantt.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx','--name','GanttServerManager','--paths',str(ROOT/'server'),'--icon',str(stage/'gantt.ico'),'--hidden-import','pystray._win32','--add-data',str(stage/'backend_server.py')+':.','--add-data',str(ROOT/'server/index.html')+':assets','--add-data',str(ROOT/'server/initial_project.json')+':assets',str(ROOT/'server/server_manager.py')]
subprocess.run(command,cwd=ROOT,check=True)
with zipfile.ZipFile(ROOT/'dist/GanttServerManager-Windows-x64.zip','w',zipfile.ZIP_DEFLATED) as out:
 out.write(ROOT/'dist/GanttServerManager.exe','GanttServerManager.exe')
 out.write(ROOT/'docs/SERVER_MANAGER.txt','사용방법.txt')
print('Windows 단일 실행파일과 배포 ZIP을 만들었습니다.')
