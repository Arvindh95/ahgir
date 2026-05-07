"""Tests for filename/header sanitization helpers."""

from app.utils.filename import attachment_content_disposition, safe_attachment_filename


def test_safe_attachment_filename_removes_header_unsafe_characters():
    filename = safe_attachment_filename('Summer/Event\r\n"Photos".zip', "photos.zip")

    assert filename == "Summer_Event_Photos_.zip"
    assert "\r" not in filename
    assert "\n" not in filename
    assert "/" not in filename
    assert '"' not in filename


def test_attachment_content_disposition_includes_ascii_and_rfc5987_names():
    header = attachment_content_disposition('Summer/Event\r\n"Photos".zip', "photos.zip")

    assert header.startswith('attachment; filename="Summer_Event_Photos_.zip"')
    assert "filename*=UTF-8''Summer_Event_Photos_.zip" in header
    assert "\r" not in header
    assert "\n" not in header
