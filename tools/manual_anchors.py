"""Record every current manual anchor as published (manual/anchors.yaml). Run after adding topics or headings."""

from baton import manual

if __name__ == "__main__":
    print(manual.Manual().write_anchors())
