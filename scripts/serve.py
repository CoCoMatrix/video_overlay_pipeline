#!/usr/bin/env python3
"""Private cloud video dashboard launcher. Python standard library only."""
import argparse, contextlib, datetime, fcntl, json, os, re, signal, socket
import subprocess, sys, time, urllib.request
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(os.environ.get('VIDEO_OVERLAY_RUNTIME', str(Path.home() / '.cache/video-overlay')))
CANDIDATES = []
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CHILDREN = []

def data_root(explicit):
    choices = [Path(explicit).expanduser()] if explicit else CANDIDATES
    for p in choices:
        if all((p / n).is_file() for n in ('index.html', 'dataset.json', 'summary.json', 'pipeline_data.csv')):
            return p.resolve()
    raise RuntimeError('找不到完整网页数据。请使用 --data-dir 指定云端结果目录。')

def expected(data):
    s = json.loads((data / 'summary.json').read_text())
    if not s.get('dataset_id') or not isinstance(s.get('samples'), int) or s['samples'] <= 0:
        raise RuntimeError('summary.json 缺少有效 dataset_id/samples。')
    return s['dataset_id'], s['samples']

def healthy(port, identity):
    try:
        with OPENER.open('http://127.0.0.1:%d/summary.json' % port, timeout=4) as r:
            if r.status != 200: return False
            value = json.load(r)
        return (value.get('dataset_id'), value.get('samples')) == identity
    except Exception:
        return False

def runtime_root(port, explicit):
    if explicit:
        return Path(explicit).expanduser().resolve()
    roots = [ROOT / 'web-runtime', Path.home() / '.cache' / 'video-review-cloud']
    for p in roots:
        try:
            p.mkdir(parents=True, exist_ok=True)
            if os.access(p, os.W_OK):
                return p if port == 8766 else p / ('port-%d' % port)
        except OSError:
            pass
    raise RuntimeError('没有可写的云端运行目录；请用 --runtime-dir 指定。')

def ensure(data, port, runtime):
    CHILDREN[:] = [p for p in CHILDREN if p.poll() is None]
    identity = expected(data)
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'ensure.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if healthy(port, identity):
            return False
        try:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
        except OSError:
            raise RuntimeError('云端端口 %d 已被其他服务或不同数据批次占用；未停止该服务。请换 --port 并同步修改 SSH 转发目标端口。' % port)
        with (runtime / 'server.log').open('ab') as log:
            p = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), '--serve',
                 '--data-dir', str(data), '--port', str(port)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        CHILDREN.append(p)
        (runtime / 'server.pid').write_text(str(p.pid))
        for _ in range(40):
            if healthy(port, identity):
                (runtime / 'launcher-status.json').write_text(json.dumps({
                    'dataset_id': identity[0], 'samples': identity[1],
                    'data_dir': str(data), 'port': port, 'pid': p.pid,
                    'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
                }, ensure_ascii=False, indent=2))
                return True
            if p.poll() is not None:
                raise RuntimeError('网页服务启动失败；请查看 ' + str(runtime / 'server.log'))
            time.sleep(.25)
        p.terminate()
        raise RuntimeError('网页服务未通过健康检查；请查看 ' + str(runtime / 'server.log'))

class Handler(SimpleHTTPRequestHandler):
    server_version = 'VideoReview/1.0'
    def send_head(self):
        self.remaining = None
        path = Path(self.translate_path(self.path))
        root = Path(self.directory).resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError:
            self.send_error(403); return None
        if path.is_dir():
            return super().send_head()
        try:
            f = path.open('rb')
        except OSError:
            self.send_error(404); return None
        size = os.fstat(f.fileno()).st_size
        start, end = 0, size - 1
        value = self.headers.get('Range')
        if value:
            m = re.fullmatch(r'bytes=(\d*)-(\d*)', value.strip())
            valid = bool(m and any(m.groups()) and size)
            if valid:
                a, b = m.groups()
                if a:
                    start = int(a); end = min(int(b) if b else size-1, size-1)
                else:
                    count = int(b)
                    valid = count > 0
                    start = max(0, size-count)
                valid = valid and start <= end and start < size
            if not valid:
                f.close()
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % size)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
        self.send_response(206 if value else 200)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(max(0,end-start+1)))
        self.send_header('Cache-Control', 'no-store')
        if value:
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start,end,size))
        self.end_headers()
        f.seek(start); self.remaining=max(0,end-start+1)
        return f
    def copyfile(self, source, output):
        if self.remaining is None:
            return super().copyfile(source, output)
        left = self.remaining
        try:
            while left:
                chunk=source.read(min(left, 1048576))
                if not chunk: break
                output.write(chunk); left-=len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.remaining=None

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir', help='Cloud dashboard directory (not model input)')
    ap.add_argument('--port', type=int, default=8766, help='Cloud loopback server port')
    ap.add_argument('--local-port', type=int, default=18766, help='SSH local port to show in the printed link')
    ap.add_argument('--runtime-dir', help='Cloud writable state/log directory')
    ap.add_argument('--wait', action='store_true', help='Keep SSH session open and restore a crashed web server')
    ap.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args=ap.parse_args()
    if not all(1024<=p<=65535 for p in (args.port,args.local_port)):
        ap.error('Ports must be 1024..65535')
    data=data_root(args.data_dir)
    if args.serve:
        from functools import partial
        server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(data)))
        print('Cloud dashboard:',data, 'loopback port:',args.port,flush=True)
        server.serve_forever()
        return
    runtime=runtime_root(args.port,args.runtime_dir)
    created=ensure(data,args.port,runtime)
    identity=expected(data)
    print('云端网页已%s：%s，%d 条。' % ('启动' if created else '就绪',identity[0],identity[1]),flush=True)
    print('在本机浏览器打开：http://127.0.0.1:%d/' % args.local_port,flush=True)
    print('视频、计算和结果保留在云端；本机仅通过 SSH 浏览。',flush=True)
    if args.wait:
        print('保持此终端打开；Ctrl+C 断开本机转发。网络断线后重新运行同一条 SSH 命令。',flush=True)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        try:
            while True:
                time.sleep(5)
                if not healthy(args.port,identity):
                    if ensure(data,args.port,runtime):
                        print('云端网页服务已恢复。',flush=True)
        except KeyboardInterrupt:
            print('\n本机转发已结束；云端网页服务保持运行。',flush=True)

if __name__=='__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as e:
        print('启动失败：'+str(e),file=sys.stderr,flush=True)
        sys.exit(1)
