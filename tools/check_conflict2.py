import sqlite3, pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect(r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\database.db')
c = conn.cursor()

# Check ODS GWP codes vs existing
f = r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\溫室氣體盤查作業相關代碼檔V2 (4).ods'
df = pd.read_excel(f, sheet_name=1, engine='odf')
ods_gwp = df.iloc[:, 41:47].dropna(how='all')
ods_gwp = ods_gwp.iloc[:, 1:5].dropna(subset=[df.columns[42]])
ods_gwp.columns = ['formula', 'gas_name', 'gwp_value', 'note']
ods_gwp['gwp_value'] = pd.to_numeric(ods_gwp['gwp_value'], errors='coerce')

print(f"ODS GWP formulas count: {len(ods_gwp)}")

# Find overlap
existing = set()
c.execute("SELECT formula FROM gwpreference")
for r in c.fetchall():
    existing.add(r[0])

ods_codes = set(ods_gwp['formula'].astype(str).str.strip())
overlap = existing & ods_codes
new_codes = ods_codes - existing
print(f"Existing GWP formulas: {len(existing)}")
print(f"ODS GWP formulas: {len(ods_codes)}")
print(f"Overlap (same formula): {len(overlap)}")
print(f"New formulas: {len(new_codes)}")
if overlap:
    print(f"  Overlapping: {sorted(overlap)[:10]}...")
if new_codes:
    # Show new ones
    new_rows = ods_gwp[ods_gwp['formula'].astype(str).str.strip().isin(new_codes)]
    print(f"  New samples:")
    for _, r in new_rows.head(10).iterrows():
        print(f"    {str(r['formula']):>10} | {str(r['gas_name']):<50} | GWP={r['gwp_value']}")

# Check GWP value differences
print("\n--- GWP value differences ---")
for code in overlap:
    c.execute("SELECT gwp_value, version FROM gwpreference WHERE formula=?", (code,))
    db_val, version = c.fetchone()
    ods_val = ods_gwp[ods_gwp['formula'].astype(str).str.strip() == code]['gwp_value'].values[0]
    if float(db_val) != float(ods_val):
        name = ods_gwp[ods_gwp['formula'].astype(str).str.strip() == code]['gas_name'].values[0]
        print(f"  {code:>10} | {str(name):<50} | DB={db_val} | ODS={ods_val}")

conn.close()
