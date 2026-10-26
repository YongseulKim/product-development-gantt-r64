"""Windows desktop launcher; --server-worker never imports Tk or opens a window."""
from __future__ import annotations
import argparse, json, os, queue, socket, sys, threading, time, traceback, urllib.request, webbrowser
from datetime import datetime
from pathlib import Path
from manager_runtime import ServerProcess, default_folder, worker

VERSION = '1.0.0'

class ManagerApp:
    def __init__(self, root, folder, port=8000, autostart=True):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        from tkinter.scrolledtext import ScrolledText
        self.tk, self.ttk, self.dialog, self.messagebox = tk, ttk, filedialog, messagebox
        self.root = root; self.controller = ServerProcess(); self.bus = queue.Queue(); self.state = 'stopped'
        self.stopping = False; self.restart_after = False; self.exit_after = False; self.tray = None; self.closed = False
        self.log_offset = 0; self.log_buffer = b''; self.presence_mtime = None; self.health_pending = False; self.last_health = 0; self.healthy = True
        self.folder = tk.StringVar(value=str(Path(folder).resolve())); self.port = tk.StringVar(value=str(port)); self.status = tk.StringVar(value='중지됨')
        self.local_url = tk.StringVar(value=f'http://localhost:{port}'); self.share_url = tk.StringVar(value='서버를 시작하면 접속 주소가 표시됩니다.'); self.clients = tk.StringVar(value='접속 중 0개 IP')
        root.title(f'상품개발 간트차트 · 서버 관리 {VERSION}'); root.geometry('960x720'); root.minsize(760, 560)
        style = ttk.Style(root); style.theme_use('vista' if os.name == 'nt' else 'clam'); style.configure('.', font=('맑은 고딕', 10))
        frame = ttk.Frame(root, padding=16); frame.pack(fill='both', expand=True); frame.columnconfigure(1, weight=1); frame.rowconfigure(6, weight=1)
        ttk.Label(frame, text='상품개발 서버 관리', font=('맑은 고딕', 17, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 14))
        ttk.Label(frame, textvariable=self.status, foreground='#245785').grid(row=0, column=3, sticky='e')
        ttk.Label(frame, text='서버 폴더').grid(row=1, column=0, sticky='w')
        self.folder_entry = ttk.Entry(frame, textvariable=self.folder); self.folder_entry.grid(row=1, column=1, columnspan=2, sticky='ew', padx=8)
        self.browse = ttk.Button(frame, text='폴더 선택', command=self.choose_folder); self.browse.grid(row=1, column=3, sticky='e')
        line = ttk.Frame(frame); line.grid(row=2, column=0, columnspan=4, sticky='ew', pady=12)
        ttk.Label(line, text='포트').pack(side='left'); self.port_entry = ttk.Entry(line, textvariable=self.port, width=8); self.port_entry.pack(side='left', padx=(8, 18))
        self.start_button = ttk.Button(line, text='서버 시작', command=self.start); self.start_button.pack(side='left', padx=3)
        self.stop_button = ttk.Button(line, text='중지', command=self.stop); self.stop_button.pack(side='left', padx=3)
        self.restart_button = ttk.Button(line, text='재시작', command=self.restart); self.restart_button.pack(side='left', padx=3)
        self.background_button = ttk.Button(line, text='백그라운드 실행', command=self.hide_to_tray); self.background_button.pack(side='left', padx=(12, 3))
        ttk.Button(line, text='종료', command=self.request_exit).pack(side='right')
        urls = ttk.LabelFrame(frame, text='접속 주소', padding=10); urls.grid(row=3, column=0, columnspan=4, sticky='ew'); urls.columnconfigure(1, weight=1)
        ttk.Label(urls, text='이 PC').grid(row=0, column=0, sticky='w'); ttk.Entry(urls, textvariable=self.local_url, state='readonly').grid(row=0, column=1, sticky='ew', padx=8)
        ttk.Button(urls, text='화면 열기', command=lambda: webbrowser.open(self.local_url.get())).grid(row=0, column=2)
        ttk.Label(urls, text='공유 주소').grid(row=1, column=0, sticky='w', pady=(7, 0)); ttk.Label(urls, textvariable=self.share_url).grid(row=1, column=1, columnspan=2, sticky='w', padx=8, pady=(7, 0))
        people = ttk.LabelFrame(frame, text='접속자 현황', padding=10); people.grid(row=4, column=0, columnspan=4, sticky='ew', pady=12)
        ttk.Label(people, textvariable=self.clients).pack(anchor='w')
        self.client_tree = ttk.Treeview(people, columns=('ip', 'seen'), show='headings', height=4)
        self.client_tree.heading('ip', text='IP 주소'); self.client_tree.heading('seen', text='마지막 응답'); self.client_tree.column('ip', width=300); self.client_tree.column('seen', width=180); self.client_tree.pack(fill='x', pady=5)
        ttk.Label(people, text='열린 화면이 보내는 신호 기준 · 60초 이상 응답이 없으면 목록에서 제외', foreground='#737373').pack(anchor='w')
        bar = ttk.Frame(frame); bar.grid(row=5, column=0, columnspan=4, sticky='ew'); ttk.Label(bar, text='서버 로그').pack(side='left'); ttk.Button(bar, text='로그 폴더 열기', command=self.open_logs).pack(side='right')
        self.log_text = ScrolledText(frame, height=12, wrap='word', font=('맑은 고딕', 9), state='disabled'); self.log_text.grid(row=6, column=0, columnspan=4, sticky='nsew', pady=(6, 8))
        ttk.Label(frame, text='창 닫기(X): 백그라운드 전환  |  종료 버튼: 서버까지 중지', foreground='#737373').grid(row=7, column=0, columnspan=4, sticky='w')
        root.protocol('WM_DELETE_WINDOW', self.on_close); root.report_callback_exception = self.callback_error
        self.buttons(); self.append('관리 창을 열었습니다. 기존 HTML과 data 폴더는 그대로 사용합니다.'); root.after(150, self.poll)
        if autostart: root.after(250, self.start)
    def append(self, text):
        if self.closed: return
        self.log_text.configure(state='normal'); self.log_text.insert('end', f'[{datetime.now():%H:%M:%S}] {text}\n')
        if int(self.log_text.index('end-1c').split('.')[0]) > 2500: self.log_text.delete('1.0', '501.0')
        self.log_text.see('end'); self.log_text.configure(state='disabled')
    def callback_error(self, *exc):
        self.append('관리 창 처리 중 오류가 발생했습니다. ' + str(exc[1]))
        path = Path(self.folder.get()) / 'logs' / 'manager-error.log'
        try: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(''.join(traceback.format_exception(*exc)), encoding='utf-8')
        except OSError: pass
    def buttons(self):
        active = self.controller.process is not None and self.controller.process.poll() is None
        self.start_button.configure(state='disabled' if active or self.stopping else 'normal')
        for button in (self.stop_button, self.restart_button, self.background_button): button.configure(state='normal' if active and not self.stopping else 'disabled')
        for field in (self.folder_entry, self.port_entry, self.browse): field.configure(state='disabled' if active or self.stopping else 'normal')
    def choose_folder(self):
        folder = self.dialog.askdirectory(initialdir=self.folder.get(), title='index.html과 data 폴더가 있는 서버 폴더')
        if folder: self.folder.set(folder)
    def start(self):
        if self.controller.process and self.controller.process.poll() is None: return
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535: raise ValueError()
        except ValueError: self.messagebox.showerror('포트 확인', '포트는 1~65535 사이의 숫자로 입력해 주세요.', parent=self.root); return
        try:
            path = self.controller.start(self.folder.get(), port)
            self.state = 'starting'; self.status.set('시작 중…'); self.local_url.set(f'http://localhost:{port}')
            self.log_offset = 0; self.log_buffer = b''; self.presence_mtime = None; self.last_health = 0; self.healthy = True
            self.client_tree.delete(*self.client_tree.get_children()); self.clients.set('접속 중 0개 IP')
            self.append(f'서버 시작 요청 · 포트 {port}'); self.append(f'로그 파일 · {path.with_suffix(".log")}')
        except Exception as error: self.state = 'error'; self.status.set('시작 실패'); self.append('서버 실행 준비에 실패했습니다. ' + str(error))
        self.buttons()
    def stop(self):
        if self.stopping: return
        if not self.controller.process or self.controller.process.poll() is not None:
            self.finish_stop(False); return
        self.stopping = True; self.state = 'stopping'; self.status.set('중지 중…'); self.append('서버 중지를 요청합니다.'); self.buttons()
        def run():
            forced = self.controller.stop(); self.bus.put(('stopped', forced))
        threading.Thread(target=run, daemon=True).start()
    def restart(self):
        if self.stopping: return
        self.restart_after = True; self.append('서버 재시작을 요청했습니다.'); self.stop()
    def finish_stop(self, forced):
        self.stopping = False; self.state = 'stopped'; self.status.set('중지됨')
        if forced: self.append('응답이 없어 서버 프로세스를 강제로 종료했습니다. 저장된 데이터는 다음 실행에서 다시 읽습니다.')
        self.client_tree.delete(*self.client_tree.get_children()); self.clients.set('접속 중 0개 IP'); self.buttons()
        if self.exit_after: self.finish_exit()
        elif self.restart_after: self.restart_after = False; self.root.after(150, self.start)
    def read_events(self):
        path = self.controller.log_path
        if not path or not path.exists(): return
        with path.open('rb') as file:
            file.seek(self.log_offset); self.log_buffer += file.read(); self.log_offset = file.tell()
        while b'\n' in self.log_buffer:
            line, self.log_buffer = self.log_buffer.split(b'\n', 1)
            try: event = json.loads(line)
            except ValueError: continue
            self.append(event['message'])
            if event['type'] == 'ready':
                self.state = 'running'; self.status.set('실행 중'); urls = event.get('addresses', []); self.share_url.set('  /  '.join(u for u in urls if '127.0.0.1' not in u) or '같은 PC에서는 위 주소를 사용하세요.'); self.buttons()
            elif event['type'] == 'error' and self.state == 'starting': self.status.set('시작 실패 · 로그 확인')
        presence = path.with_suffix('.presence.json')
        if presence.exists() and presence.stat().st_mtime_ns != self.presence_mtime:
            try: rows = json.loads(presence.read_text(encoding='utf-8'))
            except (OSError, ValueError): return
            self.presence_mtime = presence.stat().st_mtime_ns; self.client_tree.delete(*self.client_tree.get_children())
            for row in rows: self.client_tree.insert('', 'end', values=(row['ip'], datetime.fromtimestamp(row['lastSeen']).strftime('%H:%M:%S')))
            self.clients.set(f'접속 중 {len(rows)}개 IP')
    def check_health(self):
        if self.health_pending or self.state != 'running' or time.monotonic() - self.last_health < 5: return
        self.last_health = time.monotonic(); self.health_pending = True; pid = self.controller.process.pid; url = self.local_url.get() + '/api/projects'
        def run():
            ok = False
            try:
                request = urllib.request.Request(url, headers={'X-Gantt-Manager': 'healthcheck'})
                with urllib.request.urlopen(request, timeout=2) as response: ok = response.status == 200
            except Exception: pass
            self.bus.put(('health', (pid, ok)))
        threading.Thread(target=run, daemon=True).start()
    def poll(self):
        if self.closed: return
        try: self.read_events()
        except OSError: pass
        while True:
            try: kind, value = self.bus.get_nowait()
            except queue.Empty: break
            if kind == 'stopped': self.finish_stop(value)
            elif kind == 'show': self.show()
            elif kind == 'restart': self.restart()
            elif kind == 'quit': self.show(); self.request_exit()
            elif kind == 'health':
                self.health_pending = False; pid, ok = value
                if self.state == 'running' and self.controller.process.pid == pid:
                    if ok != self.healthy: self.append('서버 응답이 정상으로 돌아왔습니다.' if ok else '서버 응답이 지연되고 있습니다. 필요하면 재시작해 주세요.')
                    self.healthy = ok; self.status.set('실행 중' if ok else '응답 지연 · 재시작 가능')
        process = self.controller.process
        if process and process.poll() is not None and not self.stopping and self.state in ('starting', 'running'):
            self.state = 'error' if process.returncode else 'stopped'; self.status.set('서버 종료 · 로그 확인' if process.returncode else '중지됨'); self.append(f'서버 프로세스 종료 · 종료 코드 {process.returncode}'); self.buttons()
        self.check_health()
        if not self.closed: self.root.after(200, self.poll)
    def make_tray(self):
        if self.tray: return
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (64, 64), '#183769'); draw = ImageDraw.Draw(image)
        for y, start, end in [(15, 10, 37), (29, 22, 55), (43, 12, 46)]: draw.rounded_rectangle((start, y, end, y + 8), radius=2, fill='white')
        def post(kind): return lambda *args: self.bus.put((kind, None))
        menu = pystray.Menu(pystray.MenuItem('관리 창 열기', post('show'), default=True), pystray.MenuItem('서버 재시작', post('restart')), pystray.MenuItem('종료', post('quit')))
        self.tray = pystray.Icon('ProductGanttServer', image, '상품개발 간트차트 서버', menu); self.tray.run_detached()
    def hide_to_tray(self):
        try: self.make_tray()
        except Exception as error: self.append('백그라운드 아이콘을 만들지 못했습니다. 창을 유지합니다. ' + str(error)); return False
        self.root.withdraw(); self.append('백그라운드로 전환했습니다. 알림 영역 아이콘에서 관리 창을 다시 열 수 있습니다.'); return True
    def show(self): self.root.deiconify(); self.root.lift(); self.root.focus_force()
    def on_close(self):
        if self.controller.process and self.controller.process.poll() is None: self.hide_to_tray()
        else: self.request_exit()
    def open_logs(self):
        path = Path(self.folder.get()) / 'logs'; path.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt': os.startfile(str(path))
        else: webbrowser.open(path.as_uri())
    def request_exit(self):
        active = self.controller.process and self.controller.process.poll() is None
        if active and not self.messagebox.askyesno('서버 종료', '서버를 중지하고 관리 프로그램을 종료할까요?', parent=self.root): return
        self.exit_after = True; self.restart_after = False; self.stop()
    def finish_exit(self):
        self.closed = True
        if self.tray: self.tray.stop(); self.tray = None
        self.root.destroy()

def self_test(folder, report):
    """Exercise the frozen Windows GUI and worker, including tray, restart and persistence."""
    import tkinter as tk
    checks = []; root = tk.Tk(); app = ManagerApp(root, folder, 0, False)
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    app.port.set(str(port)); url = f'http://127.0.0.1:{port}'; deadline = time.monotonic() + 120
    def wait(predicate):
        while time.monotonic() < deadline:
            root.update()
            if predicate(): return
            time.sleep(.05)
        raise AssertionError('작동 확인 시간 초과: ' + app.status.get())
    def check(name, ok):
        if not ok: raise AssertionError(name)
        checks.append(name)
    def get(path):
        with urllib.request.urlopen(url + path, timeout=5) as response: return response.read()
    success = False
    try:
        app.start(); wait(lambda: app.state == 'running')
        check('Python 설치 경로 없이 서버 시작', app.controller.process.poll() is None)
        check('서버도 동일한 내장 실행파일로 시작', Path(app.controller.process.args[0]).resolve()==Path(sys.executable).resolve())
        check('초기 파일과 데이터 자동 준비', (Path(folder)/'index.html').exists() and (Path(folder)/'data/projects.json').exists())
        check('브라우저 화면에 접속자 신호 포함', b'gantt-manager-presence' in get('/'))
        get('/api/server/heartbeat?tab=smoke-a'); get('/api/server/heartbeat?tab=smoke-b'); wait(lambda: len(app.client_tree.get_children()) == 1)
        check('같은 IP의 여러 화면은 하나로 표시', app.client_tree.item(app.client_tree.get_children()[0])['values'][0] == '127.0.0.1')
        projects = json.loads(get('/api/projects'))['projects']; record = json.loads(get('/api/projects/' + projects[0]['id']))
        record['state']['notes'].append({'text':'실행파일 저장 확인','time':'검수'})
        request = urllib.request.Request(url+'/api/projects/'+record['id'], data=json.dumps({'version':record['version'],'state':record['state']}).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=5) as response: check('기존 저장 API 사용 가능', response.status == 200)
        check('알림 영역으로 백그라운드 전환', app.hide_to_tray()); root.update(); check('창이 숨겨져도 서버 유지', not root.winfo_viewable() and json.loads(get('/api/projects'))['projects'])
        app.show(); root.update(); check('관리 창 다시 열기', root.winfo_viewable())
        old_pid = app.controller.process.pid; app.restart(); wait(lambda: app.state=='running' and app.controller.process.pid!=old_pid)
        check('재시작 후 데이터 보존', any(n['text']=='실행파일 저장 확인' for n in json.loads(get('/api/projects/'+record['id']))['state']['notes']))
        wait(lambda: '서버 시작 완료' in app.log_text.get('1.0','end')); check('한글 로그 표시', '서버 시작 완료' in app.log_text.get('1.0','end'))
        try:
            from PIL import ImageGrab
            root.update(); time.sleep(.3); x,y=root.winfo_rootx(),root.winfo_rooty(); ImageGrab.grab((x,y,x+root.winfo_width(),y+root.winfo_height())).save(Path(report).with_suffix('.png'))
        except Exception: pass
        app.stop(); wait(lambda: app.state=='stopped'); check('중지 후 프로세스 종료', app.controller.process.poll() is not None)
        success = True
    finally:
        app.controller.emergency_stop()
        Path(report).parent.mkdir(parents=True, exist_ok=True); Path(report).write_text(json.dumps({'passed':len(checks),'success':success,'frozen':bool(getattr(sys,'frozen',False)),'checks':checks,'log':app.log_text.get('1.0','end')},ensure_ascii=False,indent=2),encoding='utf-8')
        if not app.closed: app.finish_exit()
    return 0 if success else 1

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--server-worker', action='store_true'); parser.add_argument('--data-dir', type=Path, default=default_folder()); parser.add_argument('--port', type=int, default=8000); parser.add_argument('--event-log', type=Path); parser.add_argument('--stop-file', type=Path); parser.add_argument('--no-autostart', action='store_true'); parser.add_argument('--background', action='store_true'); parser.add_argument('--self-test', action='store_true'); parser.add_argument('--test-report', type=Path)
    args = parser.parse_args()
    if args.server_worker: return worker(args.data_dir.resolve(), args.port, args.event_log, args.stop_file)
    if args.self_test: return self_test(args.data_dir.resolve(), args.test_report)
    import tkinter as tk
    root = tk.Tk(); app = ManagerApp(root, args.data_dir, args.port, not args.no_autostart)
    if args.background: root.after(400, app.hide_to_tray)
    root.mainloop(); app.controller.emergency_stop(); return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        path = default_folder()/'manager-startup-error.log'
        try: path.write_text(traceback.format_exc(), encoding='utf-8')
        except OSError: pass
        if '--self-test' in sys.argv: raise SystemExit(1)
        try:
            import tkinter.messagebox
            tkinter.messagebox.showerror('서버 관리자 실행 실패', '프로그램 실행 중 오류가 발생했습니다. manager-startup-error.log 파일을 확인해 주세요.')
        except Exception: pass
        raise
