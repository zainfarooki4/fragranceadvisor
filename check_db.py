import sqlite3

def print_function(db_path='perfumes.sqlite', limit=10):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM perfumes LIMIT ?", (limit,))
    rows = cursor.fetchall()

    for row in rows:
        print(row)
        
    conn.close()

if __name__ == "__main__":
    print_function()