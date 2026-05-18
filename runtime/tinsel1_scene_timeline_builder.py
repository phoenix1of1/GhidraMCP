#!/usr/bin/env python3
"""Build per-scene scheduler timelines from scheduler_trace_events.csv."""
import argparse, ast, collections, json
from pathlib import Path
import pandas as pd

FILM_CALLS={'BACKGROUND','PLAY','TOPPLAY','SPLAY','STAND','SWALK','WALK'}
WAIT_CALLS={'WAITFRAME','WAITTIME','EVENT'}
SOUND_CALLS={'PLAYSAMPLE','STOPSAMPLE'}
DIALOG_CALLS={'TALK','TALKAT','PRINTOBJ','PRINTTAG'}
TAG_CALLS={'SETTAG','KILLTAG','TAGACTOR'}
CONTROL_CALLS={'CONTROL','OFFSET','SCROLL','INVENTORY'}

def category(lib):
    if lib in FILM_CALLS: return 'film'
    if lib in WAIT_CALLS: return 'wait'
    if lib in SOUND_CALLS: return 'sound'
    if lib in DIALOG_CALLS: return 'dialogue_text'
    if lib in TAG_CALLS: return 'tag'
    if lib in CONTROL_CALLS: return 'control_camera_ui'
    return 'other'

def parse_args(s):
    if not isinstance(s,str) or not s.strip(): return []
    try: return json.loads(s)
    except Exception:
        try: return ast.literal_eval(s)
        except Exception: return []

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('csv', help='scheduler_trace_events.csv')
    ap.add_argument('--out', default='scene_timeline')
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    df=pd.read_csv(args.csv)
    if 'seq' not in df.columns:
        df.insert(0,'seq', range(len(df)))
    df['category']=df['libcall'].map(category)
    summary=[]
    for scene,g in df.groupby('file', sort=True):
        g=g.sort_values('seq')
        counters=collections.Counter(g['category'])
        libcounts=collections.Counter(g['libcall'])
        events=[]; films=[]
        for _,r in g.iterrows():
            film_args=r.get('film_args','') if pd.notna(r.get('film_args')) else ''
            if film_args:
                films.extend([x.strip() for x in str(film_args).split('|') if x.strip()])
            events.append({
                'seq': int(r['seq']), 'source': r.get('source',''), 'script_handle': r.get('script_handle',''),
                'ip': int(r['ip']) if pd.notna(r.get('ip')) else None, 'libcall': r.get('libcall',''),
                'category': r['category'], 'confidence': r.get('confidence',''),
                'args_display': r.get('args_display',''), 'film_args': film_args,
                'args': parse_args(r.get('args_json')),
            })
        stem=scene.replace('.SCN','')
        (out/f'{stem}.json').write_text(json.dumps({'scene':scene,'events':events,'category_counts':dict(counters),'libcall_counts':dict(libcounts),'unique_films':sorted(set(films))},indent=2))
        g[['seq','source','script_handle','ip','libcall','category','confidence','args_display','film_args']].to_csv(out/f'{stem}_timeline.csv', index=False)
        summary.append({'scene':scene,'events':len(g),'film_events':counters['film'],'wait_events':counters['wait'],'unique_films':len(set(films))})
    pd.DataFrame(summary).sort_values(['film_events','events'], ascending=False).to_csv(out/'scene_timeline_summary.csv', index=False)
if __name__ == '__main__': main()
