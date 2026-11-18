"""Local fixed-corpus retrieval comparison; no cloud calls."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tools')]
from app.config import Settings
from app.library import SearchIndex,resolve_project
from app.store import Store
from app.schemas import Project
from prepare_corpus_100 import PAPERS,load_manifest,verify_corpus
from test_corpus_100 import retrieval_report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True,choices=['baseline','optimized'])
    args=parser.parse_args()
    papers=load_manifest();verify_corpus(papers)
    cases=json.loads((ROOT/'docs/testing/agent-capability-cases.json').read_text(encoding='utf-8'))['cases']
    config=Settings(_env_file=None,workspace_root=ROOT,allowed_roots=[ROOT],runtime_dir=ROOT/'data/runtime/corpus-benchmark')
    project=Project(id='retrieval-benchmark',name='Retrieval benchmark',workingDirectory=str(ROOT),knowledgePaths=[str(PAPERS)])
    result=asyncio.run(retrieval_report(config,papers,cases,project))
    if hasattr(SearchIndex,'search_many'):
        cached=Store(config.runtime_dir).papers(resolve_project(project,config).id)
        by_digest={p['sha256']:p['key'] for p in papers}
        by_id={row['id']:by_digest[row['digest']] for row in cached.values()}
        index=SearchIndex([chunk for row in cached.values() for chunk in row['chunks']])
        for row,case in zip(result['cases'],cases):
            queries=[case['question'],*case.get('subquestions',[])]
            selected=index.rank_papers(queries)[:10]
            scoped=SearchIndex([chunk for ident,row in cached.items() if row['id'] in selected for chunk in row['chunks']])
            old_hits=scoped.search(case['question'],6)
            hits=scoped.search_many(queries,6)
            keys={(by_id[h['paper']['id']],h['page']) for h in hits}
            gold={(e['key'],e['page']) for e in case['evidence']}
            old_keys={(by_id[h['paper']['id']],h['page']) for h in old_hits}
            row['previous_scoped_question_top_6']={'hits':sorted(old_keys),'gold_pages_found':len(gold & old_keys),'gold_pages_total':len(gold)}
            row['scoped_subquestions_top_6']={'hits':sorted(keys),
                'gold_pages_found':len(gold & keys),'gold_pages_total':len(gold)}
    for variant in ('question_top_6','english_terms_top_6','previous_scoped_question_top_6','scoped_subquestions_top_6'):
        found=sum(c.get(variant,{}).get('gold_pages_found',0) for c in result['cases'])
        total=sum(c.get(variant,{}).get('gold_pages_total',0) for c in result['cases'])
        print(variant,found,'/',total,flush=True)
    path=ROOT/f'data/manual-test-results/corpus-100-{args.label}.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SAVED',path,flush=True)

if __name__=='__main__':main()
