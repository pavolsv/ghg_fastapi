import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

f = r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\溫室氣體排放係數管理表6.0.4(修) (4).ods'

# Sheet 1: CO2
print("=== Sheet 1: CO2 ===")
df = pd.read_excel(f, sheet_name='1_固定源與移動源(燃料)CO2排放係數', engine='odf', header=None)
# Data starts from row 6 (0-indexed), after 4 header rows + 1 blank
data = df.iloc[6:]
# Show all rows, columns 0-3 for key info
print(data.iloc[:, [0,1,2,3,8,12,13,14,15]].to_string())

print("\n=== Sheet 4: GWP ===")
df4 = pd.read_excel(f, sheet_name='4_含氟氣體之GWP值', engine='odf', header=None)
data4 = df4.iloc[1:]
print(data4.iloc[:, [0,1,2,3,4,5,6]].head(30).to_string())
