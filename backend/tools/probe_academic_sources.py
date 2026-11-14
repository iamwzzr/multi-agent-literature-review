"""Live arXiv service integration only; no model calls or model credentials sent."""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.store import Store
from app.research.contracts import Budget
from app.research.sources import AcademicSources
from app.research.workspace import Workspace, Meter

ROOT=Path(__file__).resolve().parents[2]


async def main():
    out=ROOT/'data/manual-test-results/academic-source-probe'
    out.mkdir(parents=True,exist_ok=True)
    config=Settings(_env_file=None,workspace_root=ROOT,allowed_roots=[ROOT],runtime_dir=out/'runtime')
    store=Store(config.runtime_dir)
    ws=Workspace(store,'source-probe','source-'+uuid4().hex)
    sources=AcademicSources(config,ws,Meter(Budget(documents=1),ws))
    papers,gaps=await sources.discover('ti:"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"','online')
    result={'executed_at':datetime.now(timezone.utc).isoformat(),'scope':'Live service integration; not online report acceptance',
            'candidates':papers,'gaps':gaps,'paid_model_calls':0}
    candidates=[p for p in papers if p['identity_status']=='verified']
    if candidates:
        doc,error=await sources.fetch(candidates[0])
        result['fetch_error']=error
        result['document']={k:v for k,v in (doc or {}).items() if k not in ('pages','path')}
        result['result']='passed' if doc and doc['correspondence']=='matched' and not error else 'not_passed'
    else:
        result['result']='blocked'
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':
    asyncio.run(main())
