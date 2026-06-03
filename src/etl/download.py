import urllib.request
import os

WSUS_URL = "https://catalog.s.download.windowsupdate.com/microsoftupdate/v6/wsusscan/wsusscn2.cab"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalog")
CAB_PATH = os.path.join(DATA_DIR, "wsusscn2.cab")
LAST_MODIFIED_PATH = os.path.join(DATA_DIR, "last_modified.txt")


def get_remote_info():
    req = urllib.request.Request(WSUS_URL, method="HEAD")
    with urllib.request.urlopen(req) as r:
        last_modified = r.headers["Last-Modified"]
        size_mb = round(int(r.headers["Content-Length"]) / 1_000_000)
        return last_modified, size_mb


def get_local_last_modified():
    if not os.path.exists(LAST_MODIFIED_PATH):
        return None
    with open(LAST_MODIFIED_PATH) as f:
        return f.read().strip()


def save_last_modified(value):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_MODIFIED_PATH, "w") as f:
        f.write(value)


def download_cab():
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"Téléchargement en cours ({WSUS_URL})...")

    def progress(count, block_size, total_size):
        percent = min(count * block_size * 100 // total_size, 100)
        print(f"\r  {percent}% ({count * block_size // 1_000_000} MB / {total_size // 1_000_000} MB)", end="")

    urllib.request.urlretrieve(WSUS_URL, CAB_PATH, reporthook=progress)
    print("\nTéléchargement terminé.")


def main():
    print("=== Vérification du catalogue wsusscn2 ===\n")

    remote, size_mb = get_remote_info()
    local = get_local_last_modified()

    print(f"Version distante : {remote}")
    print(f"Version locale   : {local or 'aucune'}\n")

    if remote == local and os.path.exists(CAB_PATH):
        print("Le catalogue est à jour. Aucun téléchargement nécessaire.")
        return

    if local and remote != local:
        print("Une nouvelle version est disponible.")
    else:
        print("Aucune version locale détectée.")

    print(f"\nTaille du fichier : ~{size_mb} MB")
    print(f"Durée estimée     : ~{round(size_mb / 100)} min (100 Mb/s) / ~{round(size_mb / 10)} min (10 Mb/s)\n")

    choix = input("Télécharger la nouvelle version ? (o/n) : ").strip().lower()
    if choix != "o":
        print("Téléchargement annulé.")
        return

    download_cab()
    save_last_modified(remote)
    print(f"Catalogue sauvegardé dans {CAB_PATH}")


if __name__ == "__main__":
    main()