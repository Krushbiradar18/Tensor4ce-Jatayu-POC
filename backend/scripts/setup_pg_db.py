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

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
ROOT = BACKEND_DIR

# Load environment from project root first, then backend as fallback.
env_loaded = False
for env_path in (PROJECT_ROOT / ".env", BACKEND_DIR / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
        env_loaded = True
        break

if not env_loaded:
    print("Warning: .env not found in project root or backend directory. Using defaults.")

# DB Connection Config
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASSWORD", "postgres")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB   = os.environ.get("PG_DB", "jatayu")
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

        portfolio_file = ROOT / "data" / "portfolio_loans.csv"
        if not portfolio_file.exists():
            print(f"Warning: {portfolio_file} not found. Skipping portfolio table setup.")
        else:
            print(f"Loading {portfolio_file}...")
            portfolio_df = pd.read_csv(portfolio_file)
            portfolio_df.columns = [str(c).lower() for c in portfolio_df.columns]
            print("Populating table 'portfolio_loans'...")
            portfolio_df.to_sql("portfolio_loans", engine, if_exists="replace", index=False)
            print(f"✓ Successfully populated portfolio_loans with {len(portfolio_df)} rows!")
        
        # In a real environment, you'd also load mock_bank_records here
        
    except Exception as e:
        print(f"Database setup failed: {e}")
        print("\nPlease ensure:")
        print(" 1. PostgreSQL is installed and running.")
        print(" 2. psycopg2 or psycopg2-binary, and sqlalchemy are installed (pip install psycopg2-binary sqlalchemy).")
        print(" 3. Credentials are correct (export PG_PASSWORD=val).")

if __name__ == "__main__":
    run()
