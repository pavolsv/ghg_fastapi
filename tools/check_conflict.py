import sqlite3
conn = sqlite3.connect(r'C:\Users\pavol\Desktop\project\backup_fastapi-new0415\database.db')
c = conn.cursor()

# Check gwpreference
c.execute("SELECT COUNT(*), COUNT(DISTINCT formula), COUNT(DISTINCT version) FROM gwpreference")
cnt, formulas, versions = c.fetchone()
print(f"[gwpreference] 總筆數={cnt}, 不同 formula={formulas}, 版本={versions}")
c.execute("SELECT version, COUNT(*) FROM gwpreference GROUP BY version")
for row in c.fetchall():
    print(f"  版本 {row[0]}: {row[1]} 筆")
c.execute("SELECT formula, gas_name_zh, gwp_value, version FROM gwpreference LIMIT 10")
print("  Sample:")
for r in c.fetchall():
    print(f"    {r[0]:<20} {str(r[1]):<30} GWP={r[2]:>8}  ({r[3]})")

# Check appendix_reference
print()
c.execute("SELECT COUNT(*), COUNT(DISTINCT appendix_type) FROM appendix_reference")
cnt, types = c.fetchone()
print(f"[appendix_reference] 總筆數={cnt}, 不同類型={types}")
c.execute("SELECT appendix_type, COUNT(*) FROM appendix_reference GROUP BY appendix_type")
for row in c.fetchall():
    print(f"  類型 {row[0]}: {row[1]} 筆")

# Check emissionfactor
print()
c.execute("SELECT COUNT(*), COUNT(DISTINCT code) FROM emissionfactor")
cnt, codes = c.fetchone()
print(f"[emissionfactor] 總筆數={cnt}, 不同 code={codes}")

conn.close()
