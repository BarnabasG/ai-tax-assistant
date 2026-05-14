"""
Snapshot Manager: Exports and imports the Qdrant vector database.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "hmrc_pages"
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
SNAPSHOT_FILE = os.path.join(DATA_DIR, "hmrc_data.snapshot")

def export_snapshot():
    """Tells Qdrant to create a snapshot, then downloads it."""
    print("Creating snapshot...")
    # 1. Create snapshot
    resp = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/snapshots")
    if resp.status_code != 200:
        print(f"Failed to create snapshot: {resp.text}")
        sys.exit(1)
        
    data = resp.json()
    snapshot_name = data["result"]["name"]
    print(f"Snapshot created: {snapshot_name}")
    
    # 2. Download snapshot
    print(f"Downloading snapshot to {SNAPSHOT_FILE}...")
    download_url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/{snapshot_name}"
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(SNAPSHOT_FILE, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                
    print(f"Export complete! You can now share {SNAPSHOT_FILE}")

def import_snapshot():
    """Uploads a local snapshot file to Qdrant and restores it."""
    if not os.path.exists(SNAPSHOT_FILE):
        print(f"Error: {SNAPSHOT_FILE} not found. Please place the snapshot file there.")
        sys.exit(1)
        
    print(f"Uploading {SNAPSHOT_FILE} to Qdrant (this may take a minute)...")
    
    # Use the upload endpoint which handles the file transfer and recovery
    url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/upload?priority=true"
    
    with open(SNAPSHOT_FILE, 'rb') as f:
        files = {'snapshot': (os.path.basename(SNAPSHOT_FILE), f, 'application/octet-stream')}
        resp = requests.post(url, files=files)
        
    if resp.status_code == 200:
        print("Import complete! The database is now ready.")
    else:
        print(f"Failed to import: HTTP {resp.status_code}")
        print(resp.text)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python snapshot.py [export|import]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "export":
        export_snapshot()
    elif cmd == "import":
        import_snapshot()
    else:
        print(f"Unknown command: {cmd}")
