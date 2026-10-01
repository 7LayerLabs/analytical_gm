"""Readable access for future assistant sessions without screen scraping."""
import argparse,json
from department import department
from storage import current,import_snapshot

def main():
    parser=argparse.ArgumentParser(description='Read the OOTP analytics department')
    parser.add_argument('report',choices=['status','briefing','players','player','finances','quality','refresh'])
    parser.add_argument('--id',type=int);parser.add_argument('--search',default='');parser.add_argument('--snapshot');args=parser.parse_args()
    if args.report=='status':result=current()
    elif args.report=='refresh':result=import_snapshot()
    else:
        d=department(args.snapshot)
        if args.report=='briefing':result=d.briefing()
        elif args.report=='players':result=[p for p in d.profiles if args.search.lower() in p['name'].lower()][:100]
        elif args.report=='player':
            if args.id is None:parser.error('player requires --id')
            result=d.player(args.id)
        elif args.report=='finances':result=d.finances()
        else:result=d.quality()
    print(json.dumps(result,indent=2,default=str,ensure_ascii=False))

if __name__=='__main__':main()
