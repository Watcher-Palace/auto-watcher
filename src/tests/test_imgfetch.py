import pytest
from src.imgfetch import classify

def test_classify_accepts_real_image():
    assert classify(b"\xff\xd8\xff" + b"x" * 5000) == "jpg"
    assert classify(b"\x89PNG\r\n\x1a\n" + b"x" * 5000) == "png"
    assert classify(b"%PDF-1.4" + b"x" * 5000) == "pdf"

def test_classify_rejects_placeholder_and_html():
    with pytest.raises(ValueError):
        classify(b"\xff\xd8\xff" + b"x" * 100)      # 太小=占位图
    with pytest.raises(ValueError):
        classify(b"<html><body>login</body></html>" + b"x" * 5000)
