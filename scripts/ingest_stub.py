from pathlib import Path


def main() -> None:
    raw_dir = Path("data/raw")
    files = sorted(raw_dir.rglob("*"))
    docs = [f for f in files if f.is_file() and f.suffix.lower() in {".doc", ".docx", ".pdf", ".png", ".jpg", ".jpeg"}]
    print(f"Detected {len(docs)} candidate files for ingest")
    for item in docs[:10]:
        print(item.as_posix())


if __name__ == "__main__":
    main()
