$py = "C:\Users\pavol\Downloads\0224\backup_fastapi\.venv\Scripts\python.exe"
$script = @"
import sys
sys.path.insert(0, r'C:\Users\pavol\Downloads\0224\backup_fastapi')
from database import create_db_and_tables, DB_FILE
print('DB path will be:', DB_FILE)
create_db_and_tables()
print('done')
"@
& $py -c $script
