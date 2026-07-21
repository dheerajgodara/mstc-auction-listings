from scraper.text_cleanup import cleanup_ocr_text


def test_cleanup_ocr_joins_split_words():
    assert "DESULPHURISATION" in (cleanup_ocr_text("DESULPHURISA TION gypsum") or "")
    assert "annexures" in (cleanup_ocr_text("documents/a nnexures") or "")
    assert cleanup_ocr_text("normal spacing stays") == "normal spacing stays"
