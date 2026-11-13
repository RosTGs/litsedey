#!/usr/bin/env python3
"""Internal agent interface: analyze, plan, build Лицедей models from versioned recipes."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.storage import Store
from studio.assembler import analyze,plan,build

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['list','analyze','plan','build']);ap.add_argument('--project');ap.add_argument('--recipe');ap.add_argument('--data',default=str(Path(__file__).resolve().parents[1]/'data'));args=ap.parse_args()
 store=Store(args.data)
 if args.command=='list':result=store.list()
 else:
  if not args.project:ap.error('--project is required')
  p=store.load(args.project)
  if args.command=='analyze':result=analyze(p)
  else:
   if not args.recipe:ap.error('--recipe is required')
   recipe=json.loads(Path(args.recipe).read_text())
   if args.command=='plan':result=plan(p,recipe)
   else:
    p,report=build(p,recipe);store.save(p);result=dict(project_id=p['id'],name=p['name'],report=report)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if not isinstance(result,dict) or result.get('ok',True) else 1
if __name__=='__main__':raise SystemExit(main())
