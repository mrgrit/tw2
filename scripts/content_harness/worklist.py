#!/usr/bin/env python3
"""하네스 작업큐 — 안티패턴 항목을 '순서 있는 손작업 목록'으로 뽑는다.
★자동 고침 아님. 나는 이 목록을 위→아래로 하나씩 손으로(Edit) 고치고, 매번 재스캔해 카운트가 주는 걸 확인한다.
병렬·스크립트 벌크 편집 금지. 사람이 하듯 차례차례.
사용: python3 worklist.py 'contents/training/attack/lab_week*.yaml' [카테고리키워드]
"""
import sys, glob, importlib.util
spec=importlib.util.spec_from_file_location('ap', __file__.replace('worklist.py','anti_patterns.py'))
ap=importlib.util.module_from_spec(spec); spec.loader.exec_module(ap)

def build(pattern, catfilter=None):
    items=[]
    for f in sorted(glob.glob(pattern)):
        hits=ap.scan_file(f)
        for name,lst in hits.items():
            if catfilter and catfilter not in name: continue
            for line,text in lst:
                items.append((f, line, name, text))
    # 파일→줄 순서 정렬 (위에서 아래로 순차 처리)
    items.sort(key=lambda x:(x[0], x[1]))
    return items

if __name__=='__main__':
    pat=sys.argv[1]; catf=sys.argv[2] if len(sys.argv)>2 else None
    items=build(pat, catf)
    print(f"# 작업큐: {len(items)}개 항목 (하나씩 손으로 처리, 처리 후 재스캔으로 확인)")
    print(f"# 필터: {catf or '(전체)'}\n")
    cur=None
    for i,(f,line,name,text) in enumerate(items,1):
        fn=f.split('/')[-1]
        if fn!=cur: cur=fn; print(f"\n## {fn}")
        print(f"{i:4d}. L{line} [{name}]")
        print(f"      {text[:110]}")
