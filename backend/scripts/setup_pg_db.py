"""
setup_pg_db.py
==============
Initializes the PostgreSQL database for the mock bureau and bank APIs.
Reads the static backend/dataset/Mock_Bureau_Dataset.xlsx and populates the DB.
"""
import os
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# DB Connection Config
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASSWORD", "postgres")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB   = os.environ.get("PG_DB", "postgres")
DB_URI = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

def run():
    print(f"Connecting to Postgres: {PG_HOST}:{PG_PORT}/{PG_DB} as {PG_USER}")
    try:
        engine = create_engine(DB_URI)
        
        mock_file = ROOT / "dataset" / "Mock_Bureau_Dataset.xlsx"
        if not mock_file.exists():
            print(f"Error: {mock_file} not found. Please ensure the dataset exists.")
            return

        print(f"Loading {mock_file}...")
        df = pd.read_excel(mock_file)
        
        print("Populating table 'mock_bureau_records'...")
        df.columns = [str(c).lower() for c in df.columns] # lowercase columns for Postgres
        df.to_sql("mock_bureau_records", engine, if_exists="replace", index=False)
        print(f"✓ Successfully populated mock_bureau_records with {len(df)} rows!")
        
        # In a real environment, you'd also load mock_bank_records here
        
    except Exception as e:
        print(f"Database setup failed: {e}")
        print("\nPlease ensure:")
        print(" 1. PostgreSQL is installed and running.")
        print(" 2. psycopg2 or psycopg2-binary, and sqlalchemy are installed (pip install psycopg2-binary sqlalchemy).")
        print(" 3. Credentials are correct (export PG_PASSWORD=val).")

if __name__ == "__main__":
    run()
