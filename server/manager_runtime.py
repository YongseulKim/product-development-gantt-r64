"""Server process, Korean events and IP presence. No GUI or third-party imports."""
from __future__ import annotations
import argparse, atexit, importlib.util, json, os, queue, re, shutil, socket, subprocess, sys, threading, time, traceback, uuid
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PRESENCE_SECONDS = 60
HEARTBEAT = r'''<script id="gantt-manager-presence">(()=>{if(!window.GANTT_SERVER)return;const tab=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);const beat=()=>fetch('/api/server/heartbeat?tab='+encodeURIComponent(tab),{cache:'no-store'}).catch(()=>{});beat();setInterval(beat,15000);window.addEventListener('pageshow',beat);window.addEventListener('pagehide',()=>navigator.sendBeacon('/api/server/leave',new URLSearchParams({tab})));})();</script>'''

def resources():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

def default_folder():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def ensure_assets(folder):
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'initial_project.json'):
        dest = folder / name
        if dest.exists():
            continue
        source = resources() / 'assets' / name if getattr(sys, 'frozen', False) else resources() / name
        if source.resolve() == dest.resolve():
            raise FileNotFoundError(f'{name} 파일을 찾을 수 없습니다.')
        if not source.is_file(): raise FileNotFoundError(f'{name} 기본 파일을 찾을 수 없습니다.')
        # Never replace an existing production file, even when two managers start together.
        try:
            with dest.open('xb') as out, source.open('rb') as inp:
                shutil.copyfileobj(inp, out)
        except FileExistsError:
            pass
    return folder

class FolderLock:
    def __init__(self, folder): self.path = Path(folder) / '.gantt-server.lock'; self.file = None
    def acquire(self):
        self.file = self.path.open('a+b'); self.file.seek(0)
        if self.path.stat().st_size == 0: self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close(); self.file = None
            raise RuntimeError('같은 데이터 폴더의 서버가 이미 실행 중입니다. 기존 서버를 먼저 중지해 주세요.') from None
        return self
    def close(self):
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0); msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close(); self.file = None

class EventLog:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
    def emit(self, kind, message, **fields):
        event = dict(time=datetime.now().astimezone().isoformat(timespec='seconds'), type=kind, message=message, **fields)
        with self.lock:
            with self.path.open('a', encoding='utf-8') as out: out.write(json.dumps(event, ensure_ascii=False) + '\n')
            with self.path.with_suffix('.log').open('a', encoding='utf-8') as out: out.write(f"[{event['time']}] {message}\n")
        return event

class Presence:
    def __init__(self, timeout=PRESENCE_SECONDS): self.timeout = timeout; self.tabs = {}; self.lock = threading.Lock()
    def beat(self, ip, tab, now=None):
        now = time.time() if now is None else now
        with self.lock:
            new_ip = not any(key[0] == ip for key in self.tabs)
            old = self.tabs.get((ip, tab), (now, now)); self.tabs[(ip, tab)] = (old[0], now)
            return new_ip
    def leave(self, ip, tab):
        with self.lock: self.tabs.pop((ip, tab), None)
    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            self.tabs = {k: v for k, v in self.tabs.items() if now - v[1] < self.timeout}
            result = {}
            for (ip, _), (first, last) in self.tabs.items():
                row = result.setdefault(ip, {'ip': ip, 'firstSeen': first, 'lastSeen': last})
                row['firstSeen'] = min(row['firstSeen'], first); row['lastSeen'] = max(row['lastSeen'], last)
            return sorted(result.values(), key=lambda r: r['ip'])

def local_addresses(port):
    ips = {'127.0.0.1'}
    try: ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError: pass
    return [f'http://{ip}:{port}' for ip in sorted(ips) if not ip.startswith('169.254.')]

def request_label(method, path, code):
    route = urlsplit(path).path
    if method == 'GET': action = '화면 접속' if route in ('/', '/index.html') else '상품 목록 조회' if route == '/api/projects' else '상품 조회'
    else: action = '상품 이름 변경' if route.endswith('/rename') else '상품 삭제' if route.endswith('/delete') else '새 상품 등록' if route == '/api/projects' else '상품 저장'
    state = '완료' if 200 <= int(code) < 400 else '실패'
    if int(code) == 409: return f'{action} 보류 · 다른 사용자가 먼저 변경했습니다.'
    if int(code) == 404: return '요청한 페이지 또는 상품을 찾을 수 없습니다.'
    return f'{action} {state} · 응답 {code}'

def worker(folder, port, event_path, stop_path):
    events = EventLog(event_path); lock = FolderLock(folder); httpd = None; finished = threading.Event()
    try:
        lock.acquire(); ensure_assets(folder)
        bundled = resources() / ('backend_server.py' if getattr(sys, 'frozen', False) else 'server.py')
        source = Path(folder) / 'server.py'
        if not source.exists(): source = bundled
        spec = importlib.util.spec_from_file_location('gantt_backend', source)
        backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
        backend.ROOT = Path(folder); backend.DATA = Path(folder) / 'data'; backend.DB = backend.DATA / 'projects.json'
        backend.initialize(); presence = Presence(); condition = threading.Condition(); in_flight = [0]
        class Handler(backend.Handler):
            def setup(self):
                super().setup(); self.connection.settimeout(20)
            def handle(self):
                with condition: in_flight[0] += 1
                try: super().handle()
                finally:
                    with condition: in_flight[0] -= 1; condition.notify_all()
            def do_GET(self):
                if urlsplit(self.path).path == '/api/server/heartbeat':
                    tab = parse_qs(urlsplit(self.path).query).get('tab', [''])[0]
                    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', tab): return self.reply(400, {'error': '접속 정보가 올바르지 않습니다.'})
                    if presence.beat(self.client_address[0], tab): events.emit('client', f'사용자 접속 · {self.client_address[0]}')
                    return self.reply(200, {'ok': True})
                return super().do_GET()
            def do_POST(self):
                if urlsplit(self.path).path == '/api/server/leave':
                    origin = self.headers.get('Origin')
                    if origin and origin != 'http://' + self.headers.get('Host', ''): return self.reply(403, {'error': '허용되지 않은 요청입니다.'})
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 1024: return self.reply(400, {'error': '접속 정보가 올바르지 않습니다.'})
                        tab = parse_qs(self.rfile.read(size).decode('utf-8')).get('tab', [''])[0]
                        presence.leave(self.client_address[0], tab)
                    except (ValueError, UnicodeError): return self.reply(400, {'error': '접속 정보가 올바르지 않습니다.'})
                    return self.reply(200, {'ok': True})
                return super().do_POST()
            def reply(self, status, value, mime='application/json; charset=utf-8'):
                if isinstance(value, bytes) and mime.startswith('text/html'):
                    value = value.replace(b'</body>', HEARTBEAT.encode('utf-8') + b'</body>', 1)
                return super().reply(status, value, mime)
            def log_request(self, code='-', size='-'):
                if urlsplit(self.path).path in ('/api/server/heartbeat', '/api/server/leave', '/favicon.ico'): return
                if self.client_address[0] == '127.0.0.1' and self.headers.get('X-Gantt-Manager') == 'healthcheck': return
                events.emit('request', f'{self.client_address[0]} · {request_label(self.command, self.path, int(code))}', ip=self.client_address[0], status=int(code))
            def log_message(self, fmt, *args):
                events.emit('warning', '요청 처리 안내 · ' + (fmt % args))
        class Server(ThreadingHTTPServer):
            allow_reuse_address = True
            def handle_error(self, request, client_address): events.emit('error', f'요청 처리 중 오류 · {client_address[0]}', detail=traceback.format_exc())
        httpd = Server(('0.0.0.0', port), Handler)
        def watch():
            previous = set(); serialized = None
            while not finished.wait(.5):
                if Path(stop_path).exists():
                    events.emit('stopping', '서버 중지를 요청했습니다. 진행 중인 요청을 마무리합니다.'); httpd.shutdown(); return
                rows = presence.snapshot(); current = {r['ip'] for r in rows}
                for ip in previous - current: events.emit('client', f'사용자 접속 종료 · {ip}')
                previous = current; value = json.dumps(rows, ensure_ascii=False)
                if value != serialized:
                    path = Path(event_path).with_suffix('.presence.json'); temp = path.with_suffix('.tmp'); temp.write_text(value, encoding='utf-8'); os.replace(temp, path); serialized = value
        threading.Thread(target=watch, daemon=True).start()
        events.emit('ready', f'서버 시작 완료 · 포트 {port}', port=port, addresses=local_addresses(port), folder=str(folder))
        httpd.serve_forever(poll_interval=.2)
        httpd.server_close()
        with condition:
            condition.wait_for(lambda: in_flight[0] == 0, timeout=8)
        events.emit('stopped', '서버를 중지했습니다. 저장 데이터는 유지됩니다.')
        return 0
    except Exception as error:
        message = '서버를 시작하거나 실행하지 못했습니다.'
        if isinstance(error, OSError) and (getattr(error, 'winerror', None) == 10048 or error.errno in (48, 98)): message = f'포트 {port}가 사용 중입니다. 기존 서버를 중지하거나 포트를 바꿔 주세요.'
        elif isinstance(error, PermissionError): message = '서버 폴더에 쓰기 권한이 없습니다. 쓰기 가능한 폴더를 선택해 주세요.'
        elif isinstance(error, RuntimeError): message = str(error)
        events.emit('error', message, detail=traceback.format_exc()); return 1
    finally:
        finished.set()
        if httpd: httpd.server_close()
        lock.close()

class ServerProcess:
    """One worker per manager. The child writes logs, not console output."""
    def __init__(self): self.process = None; self.log_path = None; self.stop_path = None; self._job = None
    def start(self, folder, port):
        if self.process and self.process.poll() is None: raise RuntimeError('서버가 이미 실행 중입니다.')
        folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True); logs = folder / 'logs'; logs.mkdir(exist_ok=True)
        tag = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
        self.log_path = logs / ('server_' + tag + '.jsonl'); self.stop_path = logs / ('server_' + tag + '.stop')
        command = [sys.executable]
        if not getattr(sys, 'frozen', False): command.append(str(Path(__file__).with_name('server_manager.py')))
        command += ['--server-worker', '--data-dir', str(folder), '--port', str(port), '--event-log', str(self.log_path), '--stop-file', str(self.stop_path)]
        env = {**os.environ, 'PYTHONUTF8': '1'}
        if getattr(sys, 'frozen', False): env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=str(folder), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        atexit.register(self.emergency_stop)
        return self.log_path
    def stop(self, timeout=12):
        if not self.process or self.process.poll() is not None: return False
        self.stop_path.touch()
        try: self.process.wait(timeout=timeout); forced = False
        except subprocess.TimeoutExpired:
            self.emergency_stop(); forced = True
        return forced
    def emergency_stop(self):
        if not self.process or self.process.poll() is not None: return
        if os.name == 'nt': subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        else: self.process.kill()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired: pass
