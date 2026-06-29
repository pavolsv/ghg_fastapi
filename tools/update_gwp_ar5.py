"""
從 6.0.4 Sheet 4 更新 gwpreference 表的 AR5 GWP 值
"""

import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from sqlmodel import Session, select
from database import engine, create_db_and_tables
from model import GWPReference

create_db_and_tables()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTOR_FILE = os.path.join(BASE_DIR, "溫室氣體排放係數管理表6.0.4(修) (4).ods")
CODE_FILE = os.path.join(BASE_DIR, "溫室氣體盤查作業相關代碼檔V2 (4).ods")


def parse_gas_names(text):
    """從 'CO2二氧化碳' 或 'CH4甲烷' 或 'CF4，四氟化碳' 拆分英文/中文"""
    if pd.isna(text) or str(text).strip() in ('', 'nan', 'NaN'):
        return '', ''
    
    s = str(text).strip()
    
    # 嘗試用逗號拆分: "CF4，四氟化碳", "CHF2CF3，1,1,1,2,2-五氟乙烷"
    for sep in ['，', ', ']:
        if sep in s:
            parts = s.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    
    # 嘗試從英文末尾拆分 (CO2二氧化碳, CH4甲烷)
    m = re.match(r'^([A-Za-z0-9()+\-/]+)(.+)$', s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    return s, ''


def parse_ar5(val_str):
    """解析 AR5 值，回傳 (gwp_value, is_qualitative, note)"""
    if pd.isna(val_str):
        return 0.0, False, None
    
    s = str(val_str).strip().replace(',', '')
    
    if s in ('', '─', 'nan', 'NaN'):
        return 0.0, False, '無資料'
    if '停用' in s:
        return 0.0, True, '蒙特婁議定書列管物質，已停用'
    if s == '<1' or s == '< 1':
        return 0.0, True, 'GWP < 1'
    if s == '0':
        return 0.0, False, None
    
    try:
        return float(s), False, None
    except ValueError:
        return 0.0, False, f'無法解析: {s}'


def main():
    print("=" * 60)
    print("更新 GWP AR5 值 (from 6.0.4 Sheet 4)")
    print("=" * 60)
    
    df = pd.read_excel(FACTOR_FILE, sheet_name='4_含氟氣體之GWP值', engine='odf', header=None)
    gwp_data = df.iloc[1:]  # skip header
    
    updated = 0
    skipped = 0
    new_count = 0
    
    with Session(engine) as session:
        for i in range(len(gwp_data)):
            r = gwp_data.iloc[i]
            code = r.iloc[0]
            if pd.isna(code) or str(code).strip() in ('', 'nan', 'NaN'):
                continue
            
            code = str(code).strip()
            gas_text = str(r.iloc[1]) if pd.notna(r.iloc[1]) else ''
            ar5_raw = r.iloc[5]
            
            gas_zh, gas_en = parse_gas_names(gas_text)
            gwp_value, is_qual, note = parse_ar5(ar5_raw)
            
            # 檢查是否已存在（只看 formula，不限制 version）
            existing = session.exec(
                select(GWPReference).where(
                    GWPReference.formula == code
                )
            ).first()
            
            if existing:
                # 只更新 gwp_value，不蓋名稱
                existing.gwp_value = gwp_value
                existing.is_qualitative = is_qual
                if note:
                    existing.note = note
                existing.version = "AR5"
                updated += 1
            else:
                # 新 code 需要填名稱
                gwp = GWPReference(
                    formula=code,
                    gas_name_zh=gas_zh,
                    gas_name_en=gas_en,
                    gwp_value=gwp_value,
                    version="AR5",
                    is_qualitative=is_qual,
                    note=note
                )
                session.add(gwp)
                new_count += 1
            
            if gwp_value > 0 or is_qual:
                print(f'  {code:>10} | AR5={str(gwp_value):>8} | {"定性" if is_qual else "數值"} | {gas_zh:<30}')
        
        # 從 V2 補 12 筆新 code
        print("\n補 V2 新增碼...")
        df_v2 = pd.read_excel(CODE_FILE, sheet_name=1, engine='odf')
        sec10 = df_v2.iloc[:, [41,42,43,44,45]].dropna(how='all')
        sec10.columns = ['title','code','name','gwp','note']
        
        existing_codes = set(session.exec(select(GWPReference.formula)).all())
        
        for _, r in sec10.iterrows():
            code_v2 = str(r['code']).strip() if pd.notna(r['code']) else ''
            if not code_v2:
                continue
            
            gas_zh2, gas_en2 = parse_gas_names(str(r['name']))
            gwp_value2, is_qual2, note2 = parse_ar5(str(r['gwp']))
            
            if code_v2 in existing_codes:
                # 只更新 DB 值為 0 的（6.0.4 沒有的，V2 補）
                existing = session.exec(
                    select(GWPReference).where(GWPReference.formula == code_v2)
                ).first()
                if existing and existing.gwp_value == 0.0 and gwp_value2 > 0:
                    existing.gwp_value = gwp_value2
                    existing.is_qualitative = is_qual2
                    if note2:
                        existing.note = note2
                    print(f'  {code_v2:>10}更新 | AR5={gwp_value2:>8}')
                    updated += 1
            else:
                gwp = GWPReference(
                    formula=code_v2,
                    gas_name_zh=gas_zh2,
                    gas_name_en=gas_en2,
                    gwp_value=gwp_value2,
                    version="AR5",
                    is_qualitative=is_qual2,
                    note=note2 or (str(r['note']) if pd.notna(r['note']) else None)
                )
                session.add(gwp)
                print(f'  {code_v2:>10}新增 | {gas_zh2:<30} | AR5={gwp_value2:>8}')
                new_count += 1
        
        session.commit()
    
    print(f"\n更新 {updated} 筆，新增 {new_count} 筆")


if __name__ == '__main__':
    main()
