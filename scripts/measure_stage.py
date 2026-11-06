import argparse,subprocess,time,datetime,json,os,resource
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
cmd=a.command
if cmd and cmd[0]=='--':cmd=cmd[1:]
t=time.monotonic();utc=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat();start=utc()
child=subprocess.Popen(cmd,start_new_session=True)
peak=0;peak_count=0;samples=0
while child.poll() is None:
 total=0;count=0
 for f in Path('/proc').iterdir():
  if not f.name.isdigit():continue
  try:
   stat=(f/'stat').read_text().rsplit(')',1)[1].split()
   if int(stat[3])!=child.pid:continue
   total+=int(stat[21])*os.sysconf('SC_PAGE_SIZE');count+=1
  except (OSError,ValueError,IndexError):pass
 peak=max(peak,total);peak_count=max(peak_count,count);samples+=1;time.sleep(.5)
rc=child.wait();usage=resource.getrusage(resource.RUSAGE_CHILDREN)
out={'started_at':start,'completed_at':utc(),'wall_s':time.monotonic()-t,'returncode':rc,'cpu_user_s':usage.ru_utime,'cpu_system_s':usage.ru_stime,'peak_sum_rss_bytes':peak,'peak_processes':peak_count,'measurement':'Linux /proc session sum RSS sampled every 0.5s; shared pages may be counted multiple times; CPU includes waited descendant processes','samples':samples,'command':cmd}
Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(out,indent=2));print('MEASUREMENT',json.dumps(out),flush=True)
raise SystemExit(rc)
