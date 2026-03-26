import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
cur = conn.cursor()

try:
    cur.execute('ALTER TABLE "user" ADD COLUMN google_id VARCHAR(100)')
    print('google_id added')
except Exception as e:
    print('google_id:', e)

try:
    cur.execute("ALTER TABLE \"user\" ADD COLUMN auth_type VARCHAR(20) DEFAULT 'email'")
    print('auth_type added')
except Exception as e:
    print('auth_type:', e)

conn.commit()
cur.close()
conn.close()
print('Done!')