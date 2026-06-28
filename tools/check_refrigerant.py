import sys
sys.path.insert(0, '.')
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from constants.refrigerant_factors import get_refrigerant_categories

cats = get_refrigerant_categories()
print('=== 更新後的冷媒逸散率 ===')
for c in cats:
    print(f'  {c["code"]} | {c["name"]:<35} | 逸散率={c["rate"]*100:>5.1f}%')
print(f'\n總共 {len(cats)} 類設備')
