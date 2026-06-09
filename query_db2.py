import sqlite3, json
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

results = {}

# EmissionFactor counts
cursor.execute('SELECT COUNT(*) as c FROM emissionfactor')
results['emissionfactor_count'] = cursor.fetchone()['c']

# emission_types
cursor.execute('SELECT DISTINCT emission_type as t FROM emissionfactor ORDER BY t')
results['emission_types'] = [r['t'] for r in cursor.fetchall()]

# years
cursor.execute('SELECT DISTINCT year as y FROM emissionfactor ORDER BY y')
results['years'] = [r['y'] for r in cursor.fetchall()]

# units
cursor.execute('SELECT DISTINCT unit as u FROM emissionfactor ORDER BY u')
results['ef_units'] = [r['u'] for r in cursor.fetchall()]

# sample diesel 170006 or natural gas 050002
cursor.execute("SELECT code, name, original_code, gas_type, factor_value, unit, year, emission_type FROM emissionfactor WHERE original_code IN ('170006', '050002') ORDER BY original_code, year, gas_type LIMIT 20")
results['samples_170006_050002'] = [dict(r) for r in cursor.fetchall()]

# GWPReference
cursor.execute('SELECT COUNT(*) as c FROM gwpreference')
results['gwp_count'] = cursor.fetchone()['c']
cursor.execute('SELECT * FROM gwpreference LIMIT 10')
results['gwp_samples'] = [dict(r) for r in cursor.fetchall()]

# Device
cursor.execute('SELECT COUNT(*) as c FROM device')
results['device_count'] = cursor.fetchone()['c']
cursor.execute('SELECT DISTINCT unit as u FROM device ORDER BY u')
results['device_units'] = [r['u'] for r in cursor.fetchall()]
cursor.execute('SELECT * FROM device LIMIT 10')
results['device_samples'] = [dict(r) for r in cursor.fetchall()]

# ActivityData
cursor.execute('SELECT COUNT(*) as c FROM activity_data')
results['activity_count'] = cursor.fetchone()['c']
cursor.execute('SELECT DISTINCT unit as u FROM activity_data ORDER BY u')
results['activity_units'] = [r['u'] for r in cursor.fetchall()]
cursor.execute('SELECT * FROM activity_data LIMIT 10')
results['activity_samples'] = [dict(r) for r in cursor.fetchall()]

conn.close()

with open('db_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print('done')
