import urllib.request
import os

"""Download the wsusscn2.cab file if a newer version is available based on the Last-Modified header.
The CAB file is large (~1.5 GB) and contains the full Windows Update catalog, so we want to avoid unnecessary downloads.
The script checks the remote Last-Modified value against a locally saved value to determine if an update is needed.
If an update is available, it prompts the user for confirmation before downloading."""

# CONFIGURATION
WSUS_URL = "https://catalog.s.download.windowsupdate.com/microsoftupdate/v6/wsusscan/wsusscn2.cab"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalog")
CAB_PATH = os.path.join(DATA_DIR, "wsusscn2.cab")
LAST_MODIFIED_PATH = os.path.join(DATA_DIR, "last_modified.txt")


def get_remote_info():
    """Perform a HEAD request to get the Last-Modified header and Content-Length (size in bytes) of the remote CAB file."""

    req = urllib.request.Request(WSUS_URL, method="HEAD")
    with urllib.request.urlopen(req) as r:
        last_modified = r.headers["Last-Modified"]
        size_mb = round(int(r.headers["Content-Length"]) / 1_000_000)
        return last_modified, size_mb


def get_local_last_modified():
    """Read the locally saved Last-Modified value from the last download, or return None if it doesn't exist."""

    if not os.path.exists(LAST_MODIFIED_PATH):
        return None
    with open(LAST_MODIFIED_PATH) as f:
        return f.read().strip()


def save_last_modified(value):
    """Save the Last-Modified value locally for future comparisons. Creates the data directory if it doesn't exist."""

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_MODIFIED_PATH, "w") as f:
        f.write(value)


def download_cab():
    """Download the CAB file from the WSUS URL and save it to the local path. Shows a progress indicator during download."""
    
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"Download in progress ({WSUS_URL})...")

    def progress(count, block_size, total_size):
        percent = min(count * block_size * 100 // total_size, 100)
        print(f"\r  {percent}% ({count * block_size // 1_000_000} MB / {total_size // 1_000_000} MB)", end="")

    urllib.request.urlretrieve(WSUS_URL, CAB_PATH, reporthook=progress)
    print("\nDownload complete.")


def main():
    """Main function to check for updates and download the CAB file if needed."""
    
    print("=== Checking the wsusscn2 catalog ===\n")

    remote, size_mb = get_remote_info()
    local = get_local_last_modified()

    print(f"Remote version : {remote}")
    print(f"Local version   : {local or 'aucune'}\n")

    if remote == local and os.path.exists(CAB_PATH):
        print("The catalog is up to date. No download necessary.")
        return

    if local and remote != local:
        print("A new version is available.")
    else:
        print("No local version detected.")

    print(f"\nFile size : ~{size_mb} MB")
    print(f"Estimated duration : ~{round(size_mb / 100)} min (100 Mb/s) / ~{round(size_mb / 10)} min (10 Mb/s)\n")

    choix = input("Download the new version ? (o/n) : ").strip().lower()
    if choix != "o":
        print("Download canceled.")
        return

    download_cab()
    save_last_modified(remote)
    print(f"Catalog save in {CAB_PATH}")


if __name__ == "__main__":
    main()