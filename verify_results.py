import pandas as pd
import os

def verify():
    file_path = "results.xlsx"
    if not os.path.exists(file_path):
        print("results.xlsx not found.")
        return

    try:
        df = pd.read_excel(file_path)
        print(f"Loaded results.xlsx with {len(df)} rows.")
        print("-" * 30)
        
        if df.empty:
            print("DataFrame is empty.")
            return

        # Print columns to check structure
        print("Columns:", df.columns.tolist())
        print("-" * 30)

        # Check first row content
        row = df.iloc[0]
        print(f"Filename: {row.get('Filename', 'N/A')}")
        print(f"Background (preview): {str(row.get('Background', ''))[:100]}...")
        print(f"Methodology (preview): {str(row.get('Methodology', ''))[:100]}...")
        print(f"Dep. Var: {row.get('Dep. Var', 'N/A')}")
        print(f"Indep. Var: {row.get('Indep. Var', 'N/A')}")
        print(f"Controls: {row.get('Controls', 'N/A')}")
        print(f"Stata Code (preview): {str(row.get('Stata Code', ''))[:100]}...")
        
    except Exception as e:
        print(f"Error reading Excel: {e}")

if __name__ == "__main__":
    verify()
