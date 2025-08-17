import sqlite3
import json

def export_to_json(db_path='perfumes.sqlite', json_path='perfumes.json'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Select all data from perfumes table
    cursor.execute("SELECT * FROM perfumes")
    rows = cursor.fetchall()

    # Get column names from the table
    col_names = [description[0] for description in cursor.description]

    # Convert each row into a dictionary {column: value}
    data = [dict(zip(col_names, row)) for row in rows]

    # Save data to JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    conn.close()
    print(f"✅ Exported {len(data)} perfumes to {json_path}")

if __name__ == "__main__":
    export_to_json()