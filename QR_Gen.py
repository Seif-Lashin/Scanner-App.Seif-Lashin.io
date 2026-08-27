# %%
!pip install qrcode pillow pandas requests

# %%
import pandas as pd
import qrcode
from pathlib import Path

# --- CONFIGURATION ---
SHEET_ID = "Insert Sheet_ID Here"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
SHEET_FILENAME = "guests_data.csv"
OUTPUT_FOLDER = "QR code data"

# Prepare output directory
output_dir = Path(OUTPUT_FOLDER)
output_dir.mkdir(parents=True, exist_ok=True)

# Fetch latest sheet data directly over HTTP
print("Fetching live guest list from Google Sheets...")
try:
    df = pd.read_csv(CSV_URL)
    print(f"✅ Successfully loaded {len(df)} records from Google Sheets!")
except Exception as e:
    raise ConnectionError(f"Failed to fetch Google Sheet. Check Sheet ID and sharing permissions. Details: {e}")

df.head()

# %%
# Locate UUID column dynamically regardless of casing
uuid_col = next((col for col in df.columns if col.strip().lower() == 'uuid'), None)

if not uuid_col:
    raise KeyError(f"Could not find 'UUID' column. Available columns: {list(df.columns)}")

generated_count = 0

for index, row in df.iterrows():
    raw_uuid = str(row[uuid_col]).strip()
    
    if not raw_uuid or raw_uuid.lower() == 'nan':
        continue
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(raw_uuid)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    file_path = output_dir / f"{raw_uuid}.png"
    img.save(file_path)
    generated_count += 1

# Save local CSV copy for email sender script
df.to_csv(SHEET_FILENAME, index=False)

print(f"✅ Generated {generated_count} QR codes and cached data to '{SHEET_FILENAME}'.")