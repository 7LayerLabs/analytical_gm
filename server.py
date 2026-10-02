import argparse,csv,io,json,os,secrets,threading,traceback,webbrowser,time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import jev
from playstyle import generate_style
from readiness import ReadinessDesk,clubs,team_view,organization
from frontoffice import Office,office_state,save,evaluate,IDENTITIES,MODES,SKILLS,GLOSSARY
from department import department
from storage import ROOT,DATA,STATUS,current,snapshots,config,signature,start_import,watcher,read_json,write_json

JOURNAL_LOCK=threading.Lock()
PORT=8765

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        # Never log request bodies, query strings or secrets.
        pass

    def send(self,obj,status=200,content_type='application/json; charset=utf-8'):
        raw=json.dumps(obj,ensure_ascii=False,default=str,allow_nan=False).encode() if content_type.startswith('application/json') else obj if isinstance(obj,bytes) else obj.encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(raw)

    def allowed(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')

    def do_GET(self):
        try:
            if not self.allowed():return self.send({'error':'Use the local app address.'},403)
            url=urlparse(self.path);q=parse_qs(url.query);path=url.path
            def param(k,d=''):return q.get(k,[d])[0]
            if path=='/api/status':
                m=current()
                return self.send({'import':STATUS,'snapshot':m,'source':config(),'jev':jev.status(),'snapshots':snapshots()})
            if path=='/api/journal':return self.send(read_json(DATA/'journal.json',[]))
            if path.startswith('/api/'):
                d=department(param('snapshot') or None)
                if path=='/api/office':return self.send({'state':office_state(d),'identities':IDENTITIES,'modes':MODES,'skills':SKILLS,'glossary':[{'term':a,'definition':b} for a,b in GLOSSARY]})
                if path.startswith('/api/office/'):
                    o=Office(d);route=path.rsplit('/',1)[-1]
                    if route=='playstyle':return self.send(generate_style([x for x in param('identities').split(',') if x],SKILLS))
                    if route=='readiness-list':return self.send(ReadinessDesk(d,int(param('team') or d.team)).listing(param('q'),param('minor','1')=='1',param('team')=='0',max(0,int(param('offset','0'))),min(50,max(1,int(param('limit','12'))))))
                    if route=='readiness':
                        pid=int(param('id'));p=d.by_id.get(pid)
                        if not p:raise ValueError('Player unavailable in this export.')
                        return self.send(ReadinessDesk(d,int(param('team') or organization(d,p))).review(pid,param('position') or None,param('hand','vsr')))
                    if route=='home':return self.send(o.home())
                    if route=='players':
                        ps=o.candidates(param('scope','organization'),param('q'),param('kind'),param('position'));sort=param('sort','grade')
                        if sort in ['name','age','salary','grade','engine_potential']:ps.sort(key=lambda p:p.get(sort) or ('' if sort=='name' else 0),reverse=param('direction','desc')=='desc')
                        limit=min(500,max(1,int(param('limit','12'))));start=max(0,int(param('offset','0')))
                        return self.send({'players':ps[start:start+limit],'total':len(ps)})
                    if route=='player':return self.send(o.report(int(param('id')),param('position') or None))
                    if route=='roster':return self.send(o.roster(param('hand','vsr'),param('internal')=='1'))
                    if route=='league':return self.send(o.benchmarks(param('year') or None))
                    if route=='finances':return self.send(o.finances())
                    if route=='acquisition':return self.send(o.acquisitions(param('free')=='1',param('position')))
                    if route=='development':return self.send(o.development())
                if path=='/api/briefing':return self.send(d.briefing())
                if path=='/api/players':
                    ps=d.profiles;scope=param('scope','organization')
                    if scope=='organization':ps=d.own()
                    elif scope=='active':ps=d.active()
                    elif scope=='mlb':ps=[p for p in ps if p['league_id']==d.league]
                    elif scope=='draft':ps=[p for p in ps if p['draft_eligible']]
                    search=param('q').lower();kind=param('kind');position=param('position')
                    ps=[p for p in ps if search in p['name'].lower() and (not kind or p['kind']==kind) and (not position or p['position']==position)]
                    sort=param('sort','engine_percentile');allowed={'name','age','salary','score','engine_percentile','engine_potential'}
                    if sort not in allowed:sort='engine_percentile'
                    ps=sorted(ps,key=lambda p:p.get(sort) or ('' if sort=='name' else 0),reverse=param('direction','desc')=='desc')
                    start=max(0,int(param('offset','0')));limit=min(500,max(1,int(param('limit','100'))))
                    return self.send({'players':ps[start:start+limit],'total':len(ps)})
                if path=='/api/player':return self.send(d.player(int(param('id')),float(param('workload')) if param('workload') else None))
                if path=='/api/depth':return self.send(d.depth())
                if path=='/api/lineup':return self.send(d.lineup(param('hand','vsr')))
                if path=='/api/pitching-plan':return self.send(d.pitching_plan())
                if path=='/api/finances':return self.send(d.finances())
                if path=='/api/development':return self.send(d.development())
                if path=='/api/acquisition':return self.send(d.acquisition(param('position'),float(param('max_salary','100000000')),param('free')=='1'))
                if path=='/api/quality':return self.send(d.quality())
                if path=='/api/export':
                    buf=io.StringIO();fields=['id','name','age','position','team','salary','score','engine_percentile','injured','active','secondary']
                    writer=csv.DictWriter(buf,fieldnames=fields,extrasaction='ignore');writer.writeheader()
                    for p in d.own():writer.writerow({k:(' '+str(p[k]) if isinstance(p.get(k),str) and p[k].startswith(('=','+','-','@')) else p.get(k)) for k in fields})
                    return self.send(buf.getvalue(),content_type='text/csv; charset=utf-8')
                return self.send({'error':'Unknown report.'},404)
            assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/report.js':'report.js','/lab.js':'lab.js','/home.js':'home.js','/playstyle.js':'playstyle.js','/readiness.js':'readiness.js'}
            if path not in assets:return self.send({'error':'Not found'},404)
            file=ROOT/'web'/assets[path];typ={'html':'text/html','js':'text/javascript','css':'text/css'}[file.suffix[1:]]
            self.send(file.read_bytes(),content_type=typ+'; charset=utf-8')
        except (ValueError,KeyError,FileNotFoundError) as e:self.send({'error':str(e)},400)
        except Exception:
            traceback.print_exc();self.send({'error':'The report could not be generated. Check the local server log.'},500)

    def do_POST(self):
        try:
            if not self.allowed() or self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}') or self.headers.get('X-GM-Request')!='1':
                return self.send({'error':'Requests must come from the local dashboard.'},403)
            length=int(self.headers.get('Content-Length','0'))
            if length>64000:return self.send({'error':'Request too large'},413)
            body=json.loads(self.rfile.read(length) or b'{}');path=urlparse(self.path).path
            if path=='/api/office/save':return self.send(save(department(),body))
            if path=='/api/office/evaluate':return self.send(evaluate(department(),body))
            if path=='/api/import':start_import();return self.send({'message':'Checking for a completed export.'})
            if path=='/api/jev/setup':return self.send(jev.setup(body.get('key',''),bool(body.get('remember')),body.get('model','jev-latest')))
            if path=='/api/jev/forget':return self.send(jev.forget())
            if path=='/api/jev/review':return self.send(jev.review(department(),int(body['id'])))
            if path=='/api/scenario':
                send=[int(x) for x in body.get('send',[])];receive=[int(x) for x in body.get('receive',[])]
                if len(send)+len(receive)>30:raise ValueError('Use at most 30 players in a scenario.')
                price=float(body.get('war_value',8000000))
                if not 0<=price<=100000000:raise ValueError('Use a $/WAR value from 0 to 100 million.')
                return self.send(department().scenario(send,receive,price,body.get('war_assumptions',{})))
            if path=='/api/journal':
                text=str(body.get('text','')).strip()
                if not text or len(text)>10000:raise ValueError('Enter a note from 1 to 10,000 characters.')
                with JOURNAL_LOCK:
                    entries=read_json(DATA/'journal.json',[])
                    m=current();entries.insert(0,{'id':secrets.token_hex(8),'text':text,'player_id':body.get('player_id'),
                        'created_at':datetime.now(timezone.utc).isoformat(),'game_date':m['game_date'] if m else None,'snapshot':m['id'] if m else None})
                    write_json(DATA/'journal.json',entries)
                return self.send(entries)
            return self.send({'error':'Unknown action.'},404)
        except (ValueError,KeyError) as e:self.send({'error':str(e)},400)
        except Exception:
            traceback.print_exc();self.send({'error':'The action failed. Local analytics remain available.'},500)

def archive_predictions():
    # Every completed export gets a forecast, even while the GM is on another page.
    from season_projection import season_projection
    seen=set()
    while True:
        for snapshot in reversed(snapshots()):
            if snapshot['id'] in seen:continue
            try:season_projection(department(snapshot['id']))
            except (ValueError,FileNotFoundError):pass  # Unsupported evidence remains visible on the clubhouse.
            except Exception:traceback.print_exc()
            seen.add(snapshot['id'])
        time.sleep(5)


def main():
    global PORT
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--open',action='store_true');args=parser.parse_args();PORT=args.port
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    threading.Thread(target=watcher,daemon=True).start()
    threading.Thread(target=archive_predictions,daemon=True).start()
    if not current():start_import()
    url=f'http://127.0.0.1:{PORT}'
    print('OOTP Analytics Department: '+url,flush=True)
    if args.open:webbrowser.open(url)
    server.serve_forever()

if __name__=='__main__':main()
