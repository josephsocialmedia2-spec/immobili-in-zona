#!/usr/bin/env python3
import json, sys
from search_engine import _google_search
q=' '.join(sys.argv[1:]).strip() or '"36069783"'
rows,err=_google_search(q,10)
print(json.dumps({'query':q,'error':err,'count':len(rows),'results':rows[:10]},ensure_ascii=False,indent=2))
