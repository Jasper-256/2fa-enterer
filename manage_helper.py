"""Install, inspect, restart, or remove the autofill login helper."""
import argparse
import os
import plistlib
import subprocess
import time
from pathlib import Path

LABEL = 'com.jasper.2fa-autofill'
ROOT = Path(__file__).resolve().parent
AGENT = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
DOMAIN = 'gui/' + str(os.getuid())
RUNTIME = ROOT / '.runtime'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install','restart','stop','uninstall','status'])
    action = parser.parse_args().action
    if action == 'status':
        raise SystemExit(subprocess.call(['launchctl','print',DOMAIN+'/'+LABEL]))
    if action == 'restart':
        subprocess.run(['launchctl','kickstart','-k',DOMAIN+'/'+LABEL],check=True)
        return
    if action in ('stop','uninstall'):
        subprocess.run(['launchctl','bootout',DOMAIN+'/'+LABEL],check=False)
        if action == 'uninstall' and AGENT.exists():
            AGENT.unlink()
        return
    RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True)
    AGENT.parent.mkdir(parents=True,exist_ok=True)
    if AGENT.exists():
        subprocess.run(['launchctl','bootout',DOMAIN+'/'+LABEL],check=False)
    configuration = {
        'Label': LABEL,
        'ProgramArguments': ['/opt/homebrew/bin/python3.9',str(ROOT/'2fa_autofill.py'),'--daemon'],
        'WorkingDirectory': str(ROOT),
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit':False},
        'ThrottleInterval':15,
        'StandardOutPath':str(RUNTIME/'helper.log'),
        'StandardErrorPath':str(RUNTIME/'helper-error.log'),
    }
    AGENT.write_bytes(plistlib.dumps(configuration))
    subprocess.run(['launchctl','enable',DOMAIN+'/'+LABEL],check=True)
    # launchd can finish a bootout asynchronously; wait briefly if it is retiring.
    for attempt in range(10):
        result = subprocess.run(['launchctl','bootstrap',DOMAIN,str(AGENT)],capture_output=True,text=True)
        if result.returncode == 0:
            break
        if result.returncode != 5 or attempt == 9:
            raise subprocess.CalledProcessError(result.returncode,result.args,output=result.stdout,stderr=result.stderr)
        time.sleep(.2)
    print('Installed and started '+LABEL)


if __name__ == '__main__':
    main()
