"""Tests for GeM document magic validation (fail closed on HTML shells)."""

from __future__ import annotations

from scraper.gem_doc_validate import (
    extension_for_kind,
    is_gem_document_bytes,
    looks_like_gem_html_shell,
)


def test_rejects_plain_html():
    body = b"<!DOCTYPE html><html><head><title>Download Document</title></head><body>x" * 20
    assert looks_like_gem_html_shell(body)
    ok, kind, err = is_gem_document_bytes(body)
    assert not ok
    assert kind is None
    assert err in {"gem_html_shell", "gem_html_rejected"}


def test_rejects_bom_prefixed_html():
    body = b"\xef\xbb\xbf<!DOCTYPE html><html><body>" + b"y" * 600
    assert looks_like_gem_html_shell(body)
    ok, _kind, err = is_gem_document_bytes(body)
    assert not ok
    assert err


def test_rejects_session_expired_title():
    body = (
        b"<html><head><title>Session Expired</title></head>"
        b"<body>please login again</body>" + b"z" * 600
    )
    ok, _kind, err = is_gem_document_bytes(body)
    assert not ok
    assert err == "gem_session_expired"


def test_accepts_pdf():
    body = b"%PDF-1.7\n" + b"0" * 600
    ok, kind, err = is_gem_document_bytes(body)
    assert ok and kind == "pdf" and err is None
    assert extension_for_kind(kind) == "pdf"


def test_accepts_docx_pk():
    body = b"PK\x03\x04" + b"0" * 600
    ok, kind, err = is_gem_document_bytes(body)
    assert ok and kind == "docx" and err is None
    assert extension_for_kind(kind) == "docx"


def test_rejects_unknown_magic():
    body = b"\x00\x01\x02\x03" + b"Q" * 600
    ok, kind, err = is_gem_document_bytes(body)
    assert not ok
    assert kind is None
    assert err == "gem_unknown_magic"


def test_rejects_file_list_shell_without_magic():
    body = (
        b"<html><script>getFileUploadDownloadObj('/eprocure/xcommon/ajax/file-list/1/abc')"
        b"</script><title>Download Document</title></html>" + b"a" * 600
    )
    ok, _kind, err = is_gem_document_bytes(body)
    assert not ok
    assert err in {"gem_html_shell", "gem_html_rejected", "gem_session_expired"}
