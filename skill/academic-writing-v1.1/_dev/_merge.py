import yaml, sys, collections, os

BASE = r'C:\Users\appro\WorkBuddy\2026-11-11-06-47-14\academic-writing-v1.1'
frags = ['frag_qnt.yaml', 'frag_prd.yaml', 'frag_qlt.yaml', 'frag_sci.yaml', 'frag_cln.yaml']

# section 归一：v1.0 存在 method(24) 与 methods(4) 并存
SECTION_ALIAS = {'methods': 'method', 'experiments ': 'experiments'}

base = yaml.safe_load(open(os.path.join(BASE, 'rules', 'rules.yaml'), encoding='utf-8'))['rules']
print('base', len(base))

new = []
for f in frags:
    r = yaml.safe_load(open(os.path.join(BASE, 'rules', f), encoding='utf-8'))['rules']
    print(f, len(r))
    new.extend(r)

allr = base + new
seen = {}
for r in allr:
    sec = r.get('section')
    if isinstance(sec, str) and sec.strip() in SECTION_ALIAS:
        r['section'] = SECTION_ALIAS[sec.strip()]
    if r['id'] in seen:
        print('DUP ID', r['id'])
    seen[r['id']] = r

merged = list(seen.values())
print('merged', len(merged))

# 按前缀稳定排序，保持可读性
order = ['ABS', 'TIT', 'INT', 'REL', 'MET', 'SCI', 'DAT', 'EXP', 'RES', 'DIS', 'CON', 'REV', 'REB',
         'STY', 'GEN', 'ETH', 'SUB', 'REF', 'DBL', 'WRD', 'ARG', 'DSG', 'TSY', 'THE', 'VLD', 'CCL',
         'REP', 'MLD', 'QNT', 'PRD', 'RPR', 'QLT', 'CLN']
def key(r):
    pre = r['id'].split('-')[1]
    return (order.index(pre) if pre in order else 99, r['id'])
merged.sort(key=key)

header = """# 学术写作可判定规则库
# v1.1.0（2026-11-11）
# 字段：id / genre / section / rule / source / signal / fix
# 可选：track（quant|predictive|qualitative|basic-science|clinical|reporting）
#       note（提示性规则说明）/ conflict（误报豁免）/ scope（process 类非文本规则）
# section 取值统一为：abstract / title / introduction / related-work / method /
#   experiments / results / discussion / conclusion / references / rebuttal /
#   review / ethics / submission / general / chapter-structure / contribution / defense
# 纪律：写不出 signal 的规则不入库；每条必须有 source；宁缺毋滥。

rules:
"""
with open(os.path.join(BASE, 'rules', 'rules.yaml'), 'w', encoding='utf-8') as fh:
    fh.write(header)
    yaml.safe_dump({'rules': merged}, fh, allow_unicode=True, sort_keys=False,
                   default_flow_style=False, width=200)

print('written')
