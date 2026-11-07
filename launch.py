#!/usr/bin/env python3
"""Start the loopback service once, then open the editor in the default browser."""
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

root=Path(__file__).resolve().parent
url='http://127.0.0.1:18321'
def available():
    try:
        with urllib.request.urlopen(url+'/api/bootstrap',timeout=1) as response:
            return json.load(response).get('app')=='kadr-ai-studio'
    except (OSError,ValueError):
        return False
if not available():
    (root/'data').mkdir(exist_ok=True)
    with (root/'data/server.log').open('ab') as log:
        process=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root,stdout=log,stderr=log,start_new_session=True)
    (root/'data/server.pid').write_text(str(process.pid))
    for _ in range(40):
        if available():break
        if process.poll() is not None:raise SystemExit('Не удалось запустить Kadr. Подробности: data/server.log')
        time.sleep(.25)
    else:raise SystemExit('Сервер не ответил. Подробности: data/server.log')
webbrowser.open(url)
