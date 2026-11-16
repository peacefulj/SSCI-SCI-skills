import yaml, os, sys, collections

BASE = r'C:\Users\appro\WorkBuddy\2026-11-11-06-47-14\academic-writing-v1.1'
RULES = os.path.join(BASE, 'rules', 'rules.yaml')
FRAG = os.path.join(BASE, '_dev', 'fragments')

base = yaml.safe_load(open(RULES, encoding='utf-8'))['rules']
print('base rules:', len(base))
base_ids = [r['id'] for r in base]

# 1) 新规则（4 本欠梳理书目）
new_rules = yaml.safe_load(open(os.path.join(FRAG, 'frag_books.yaml'), encoding='utf-8'))['rules']
print('new rules:', len(new_rules))

# 2) 存量规则示例
examples = {}
for f in ['frag_ex_qnt.yaml', 'frag_ex_prd.yaml', 'frag_ex_qlt.yaml', 'frag_ex_rpr.yaml']:
    for e in yaml.safe_load(open(os.path.join(FRAG, f), encoding='utf-8'))['examples']:
        assert e['id'] not in examples, 'dup example ' + e['id']
        examples[e['id']] = e
print('examples:', len(examples))

# 3) 插入：QNT 区块内按 id 归并（原文件 QNT 段已按 id 有序）
qnt_idx = [i for i, r in enumerate(base) if r['id'].startswith('QNT-')]
start, end = qnt_idx[0], qnt_idx[-1] + 1
head, qnt_block, tail = base[:start], base[start:end], base[end:]
qnt_block = sorted(qnt_block + new_rules, key=lambda r: r['id'])

merged = head + qnt_block + tail

# 4) 注入示例
seen = set()
injected = 0
for r in merged:
    if r['id'] in seen:
        sys.exit('DUP ID ' + r['id'])
    seen.add(r['id'])
    if r['id'] in examples:
        r['example_bad'] = examples[r['id']]['example_bad'].strip()
        r['example_good'] = examples[r['id']]['example_good'].strip()
        injected += 1

# 5) 字段完整性
need = ['id', 'genre', 'section', 'rule', 'source', 'signal', 'fix']
for r in merged:
    miss = [k for k in need if not r.get(k)]
    if miss:
        sys.exit(f'INCOMPLETE {r["id"]}: {miss}')

with_ex = [r for r in merged if r.get('example_bad') and r.get('example_good')]

header = """# 学术写作可判定规则库
# v1.2.0（2026-11-11）
# 字段：id / genre / section / rule / source / signal / fix
# 可选：track（quant|predictive|qualitative|basic-science|clinical|reporting）
#       example_bad（违反本条的典型写法）/ example_good（改正后写法）
#       note（提示性规则说明）/ conflict（误报豁免）/ scope（process 类非文本规则）
# section 取值统一为：abstract / title / introduction / related-work / method /
#   experiments / results / discussion / conclusion / references / rebuttal /
#   review / ethics / submission / general / chapter-structure / contribution / defense
# 纪律：写不出 signal 的规则不入库；每条必须有 source；宁缺毋滥。

rules:
"""
with open(RULES, 'w', encoding='utf-8') as fh:
    fh.write(header)
    yaml.safe_dump({'rules': merged}, fh, allow_unicode=True, sort_keys=False,
                   default_flow_style=False, width=200)

print('merged:', len(merged))
print('examples injected:', injected, '/', len(examples))
print('rules with examples:', len(with_ex), f'({len(with_ex)/len(merged):.0%})')
print('with source:', sum(1 for r in merged if r.get('source')), '/', len(merged))
c = collections.Counter(r['track'] for r in merged)
print('by track:', dict(c))
