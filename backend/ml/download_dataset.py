"""Download the full canonical Apache Ant 1.7 CSV from Zenodo with checksum verification."""
from pathlib import Path
from urllib.request import Request, urlopen
from hashlib import md5

URL = "https://zenodo.org/records/268440/files/ant-1.7.csv?download=1"
EXPECTED_MD5 = "d99a6698b92553abb285df838e03dcbb"
DEST = Path(__file__).resolve().parent / "data" / "ant-1.7.csv"

def main():
    request = Request(URL, headers={"User-Agent": "ResearchReplication/1.0"})
    with urlopen(request, timeout=60) as response:
        data = response.read()
    actual = md5(data).hexdigest()
    if actual != EXPECTED_MD5:
        raise ValueError(f"Unexpected dataset MD5 {actual}; expected {EXPECTED_MD5}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(data)
    print(f"Downloaded {len(data)} bytes to {DEST}")

if __name__ == "__main__":
    main()
