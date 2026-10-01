"""Double-click launcher. Reuses the server or starts it invisibly."""
import json,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path

root=Path(__file__).resolve().parent;url='http://127.0.0.1:8765'
def available():
    try:
        with urllib.request.urlopen(url+'/api/status',timeout=2) as r:return 'snapshot' in json.load(r)
    except Exception:return False
if not available():
    logs=root/'data';logs.mkdir(exist_ok=True)
    with open(logs/'server-out.log','a',encoding='utf-8') as out,open(logs/'server-error.log','a',encoding='utf-8') as err:
        subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(30):
        if available():break
        time.sleep(.5)
if available():webbrowser.open(url)
else:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,'The analytics department could not start. Check data/server-error.log in the OOTP-Assistant folder.','Fenway Front Office',16)
