import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

f = r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\溫室氣體排放係數管理表6.0.4(修) (4).ods'
xls = pd.ExcelFile(f, engine='odf')
print(f"Sheet names: {xls.sheet_names}")
print()

for sheet in xls.sheet_names:
    df = pd.read_excel(f, sheet_name=sheet, engine='odf')
    print(f"=== [{sheet}] === ({df.shape[0]} rows x {df.shape[1]} cols)")
    for i, c in enumerate(df.columns):
        print(f"  [{i}] {repr(c)}")
    print()
    # Show first 5 rows
    print(df.head(5).to_string())
    print()
