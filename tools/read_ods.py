import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

f = r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\溫室氣體盤查作業相關代碼檔V2 (4).ods'
df = pd.read_excel(f, sheet_name=1, engine='odf')

# Section 10: GWP (cols 41-47)
print("=== Section 10: GWP ===")
sec10 = df.iloc[:, 41:47].dropna(how='all')
# columns: 41=title, 42=code, 43=name, 44=gwp_value, 45=note, 46=empty
gwp_data = sec10.iloc[:, 1:5].dropna(subset=[sec10.columns[1]])
gwp_data.columns = ['code', 'gas_name', 'gwp_value', 'note']
for _, row in gwp_data.iterrows():
    print(f"  {row['code']:>10} | {str(row['gas_name']):<50} | GWP={row['gwp_value']}")

print("\n=== Section 7: Factor Codes (sample) ===")
sec7 = df.iloc[:, 28:33].dropna(how='all')
factor_data = sec7.iloc[:, 2:4].dropna(subset=[sec7.columns[2]])
factor_data.columns = ['code', 'name']
print(f"  Total: {len(factor_data)} codes")
for _, row in factor_data.head(20).iterrows():
    print(f"  {str(row['code']):>6} | {row['name']}")

print("\n=== Section 8: Refrigerant Codes (sample) ===")
sec8 = df.iloc[:, 33:38].dropna(how='all')
refrig_data = sec8.iloc[:, 2:4].dropna(subset=[sec8.columns[2]])
refrig_data.columns = ['code', 'name']
print(f"  Total: {len(refrig_data)} codes")
for _, row in refrig_data.iterrows():
    print(f"  {str(row['code']):>8} | {row['name']}")
