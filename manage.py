#!/usr/bin/env python3
"""Install or manage the no-AI macOS LaunchAgent."""
import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('AMUL_DATA_DIR', str(Path.home() / 'Library/Application Support/AmulStockMonitor')))
PYTHON = Path(sys.executable)
LABEL = 'local.amul-stock-monitor'
DOMAIN = f'gui/{os.getuid()}'
SERVICE = f'{DOMAIN}/{LABEL}'
PLIST = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'


def launch(*args, check=True):
    return subprocess.run(['/bin/launchctl',*args],capture_output=True,text=True,check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','pause','resume','status','check'])
    args = parser.parse_args()
    if args.action in ('install','resume','pause') and PLIST.exists():
        existing = plistlib.loads(PLIST.read_bytes())
        if str(ROOT/'monitor.py') not in existing.get('ProgramArguments',[]):
            raise RuntimeError('Existing LaunchAgent belongs to another installation; manage it from that checkout')
    if args.action == 'status':
        result = launch('print',SERVICE,check=False)
        print('Schedule: enabled, every 15 minutes while awake' if result.returncode == 0 else 'Schedule: paused / not loaded')
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if any(s in line for s in ['state =','runs =','last exit code','run interval']): print(line.strip())
        if (DATA/'state.json').exists():
            data = json.loads((DATA/'state.json').read_text())
            print('Last check:', data.get('last_check'), 'PIN:',data.get('pin'))
            for key, entry in data.get('products',{}).items():
                print(key.title()+':',entry.get('observation',{}).get('status','unknown'))
            if data.get('last_error'): print('Check error:',data['last_error'])
            if data.get('notification_error'): print('Notification error:',data['notification_error'])
        return
    if args.action == 'check':
        subprocess.run([str(PYTHON),str(ROOT/'monitor.py'),'--once'],check=True)
        return
    if args.action == 'pause':
        launch('disable',SERVICE)
        launch('bootout',SERVICE,check=False)
        print('Amul stock monitoring paused.')
        return
    if args.action == 'install':
        DATA.mkdir(parents=True,exist_ok=True)
        PLIST.parent.mkdir(parents=True,exist_ok=True)
        launch('bootout',SERVICE,check=False)
        content = {'Label':LABEL,'ProgramArguments':[str(PYTHON),str(ROOT/'monitor.py'),'--once'],
                   'WorkingDirectory':str(ROOT),'RunAtLoad':True,'StartInterval':900,
                   'ProcessType':'Background','LimitLoadToSessionType':'Aqua',
                   'StandardOutPath':'/dev/null','StandardErrorPath':str(DATA/'launchd-error.log'),
                   'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin:/usr/sbin:/sbin'),
                                           'AMUL_PINCODE':os.environ.get('AMUL_PINCODE','110001'),
                                           'AMUL_DATA_DIR':str(DATA)},'Umask':63}
        PLIST.write_bytes(plistlib.dumps(content))
        PLIST.chmod(0o644)
    if not PLIST.exists():
        raise RuntimeError('Run install before resume')
    launch('enable',SERVICE)
    if launch('print',SERVICE,check=False).returncode:
        launch('bootstrap',DOMAIN,str(PLIST))
    print('Amul stock monitoring enabled: every 15 minutes, with a check at login.')


if __name__ == '__main__': main()
