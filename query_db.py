import sqlite3
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# EmissionFactor counts
cursor.execute('SELECT COUNT(*) FROM emissionfactor')
print('EmissionFactor total:', cursor.fetchone()[0])

# emission_types
cursor.execute('SELECT DISTINCT emission_type FROM emissionfactor ORDER BY emission_type')
print('Emission types:', [r[0] for r in cursor.fetchall()])

# years
cursor.execute('SELECT DISTINCT year FROM emissionfactor ORDER BY year')
print('Years:', [r[0] for r in cursor.fetchall()])

# units
cursor.execute('SELECT DISTINCT unit FROM emissionfactor ORDER BY unit')
print('Units:', [r[0] for r in cursor.fetchall()])

# sample diesel 170006 or natural gas 050002
cursor.execute("SELECT code, name, original_code, gas_type, factor_value, unit, year, emission_type FROM emissionfactor WHERE original_code IN ('170006', '050002') ORDER BY original_code, year, gas_type LIMIT 20")
print('Samples (170006, 050002):')
for r in cursor.fetchall():
    print(r)

# GWPReference
cursor.execute('SELECT COUNT(*) FROM gwpreference')
print('GWPReference total:', cursor.fetchone()[0])
cursor.execute('SELECT * FROM gwpreference LIMIT 10')
print('GWP samples:')
for r in cursor.fetchall():
    print(r)

# Device
cursor.execute('SELECT COUNT(*) FROM device')
print('Device total:', cursor.fetchone()[0])
cursor.execute('SELECT DISTINCT unit FROM device ORDER BY unit')
print('Device units:', [r[0] for r in cursor.fetchall()])
cursor.execute('SELECT * FROM device LIMIT 10')
print('Device samples:')
for r in cursor.fetchall():
    print(r)

# ActivityData
cursor.execute('SELECT COUNT(*) FROM activity_data')
print('ActivityData total:', cursor.fetchone()[0])
cursor.execute('SELECT DISTINCT unit FROM activity_data ORDER BY unit')
print('ActivityData units:', [r[0] for r in cursor.fetchall()])
cursor.execute('SELECT * FROM activity_data LIMIT 10')
print('ActivityData samples:')
for r in cursor.fetchall():
    print(r)

conn.close()
