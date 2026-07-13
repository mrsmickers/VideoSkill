import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

MODULE_PATH = Path(__file__).parent.parent / "skills" / "publish-sop" / "scripts" / "notion_sop.py"

spec = importlib.util.spec_from_file_location("notion_sop", MODULE_PATH)
notion_sop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notion_sop)


def test_md_to_blocks_maps_structures():
    md = (
        "# H1\n"
        "## H2\n"
        "### H3\n"
        "- bullet\n"
        "1. numbered\n"
        "- [ ] todo open\n"
        "- [x] todo done\n"
        "> a quote\n"
        "---\n"
        "plain paragraph\n"
    )
    blocks = notion_sop.md_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert types == [
        "heading_1", "heading_2", "heading_3",
        "bulleted_list_item", "numbered_list_item",
        "to_do", "to_do", "quote", "divider", "paragraph",
    ]
    assert blocks[5]["to_do"]["checked"] is False
    assert blocks[6]["to_do"]["checked"] is True
    assert blocks[7]["quote"]["rich_text"][0]["text"]["content"] == "a quote"


def test_md_to_blocks_skips_blank_lines():
    assert len(notion_sop.md_to_blocks("a\n\n\nb\n")) == 2


def test_parse_inline_bold_code_link_italic():
    segs = notion_sop.parse_inline("say **bold** and `code` and [link](https://x) and *it* end")
    rendered = [
        (
            s["text"]["content"],
            s.get("annotations", {}),
            (s["text"].get("link") or {}).get("url"),
        )
        for s in segs
    ]
    assert ("bold", {"bold": True}, None) in rendered
    assert ("code", {"code": True}, None) in rendered
    assert ("link", {}, "https://x") in rendered
    assert ("it", {"italic": True}, None) in rendered
    assert rendered[0][0] == "say "
    assert rendered[-1][0] == " end"


def test_rich_text_splits_over_2000_chars():
    segs = notion_sop._rich_text("x" * 4500)
    assert [len(s["text"]["content"]) for s in segs] == [2000, 2000, 500]


def test_append_blocks_chunks_at_100(mocker):
    request_mock = mocker.patch.object(notion_sop, "_request", return_value={})
    blocks = [notion_sop._block("paragraph", f"p{i}") for i in range(230)]
    notion_sop.append_blocks("page-id", blocks)
    assert request_mock.call_count == 3
    sizes = [len(call.args[2]["children"]) for call in request_mock.call_args_list]
    assert sizes == [100, 100, 30]


def test_cmd_create_sends_title_and_icon(mocker, capsys):
    request_mock = mocker.patch.object(
        notion_sop, "_request", return_value={"id": "new-id", "url": "https://n/x"}
    )
    notion_sop.cmd_create("parent-1", "My SOP", "🧠")
    method, path, payload = request_mock.call_args.args
    assert (method, path) == ("POST", "/pages")
    assert payload["parent"] == {"page_id": "parent-1"}
    assert payload["icon"] == {"type": "emoji", "emoji": "🧠"}
    assert payload["properties"]["title"]["title"][0]["text"]["content"] == "My SOP"
    out = capsys.readouterr().out
    assert "page_id=new-id" in out and "url=https://n/x" in out


def test_cmd_image_runs_three_step_upload(tmp_path, mocker, capsys):
    jpg = tmp_path / "f.jpg"
    jpg.write_bytes(b"\xff\xd8fake")
    request_mock = mocker.patch.object(
        notion_sop, "_request", return_value={"id": "up-1"}
    )
    notion_sop.cmd_image("page-1", str(jpg), "a caption")

    calls = request_mock.call_args_list
    assert calls[0].args[:2] == ("POST", "/file_uploads")
    assert calls[0].kwargs["version"] == notion_sop.UPLOAD_VERSION
    assert calls[1].args[:2] == ("POST", "/file_uploads/up-1/send")
    assert b"fake" in calls[1].kwargs["body"]
    method, path, payload = calls[2].args
    assert (method, path) == ("PATCH", "/blocks/page-1/children")
    image = payload["children"][0]["image"]
    assert image["file_upload"] == {"id": "up-1"}
    assert image["caption"][0]["text"]["content"] == "a caption"


def test_cmd_html_uploads_and_attaches_embed(tmp_path, mocker, capsys):
    html = tmp_path / "calc.html"
    html.write_text("<!doctype html><body><b>hi</b></body>")
    request_mock = mocker.patch.object(
        notion_sop, "_request", return_value={"id": "up-9"}
    )
    notion_sop.cmd_html("page-1", str(html), "ROI calculator")

    calls = request_mock.call_args_list
    method, path, payload = calls[0].args
    assert (method, path) == ("POST", "/file_uploads")
    assert payload["content_type"] == "text/html"
    assert calls[0].kwargs["version"] == notion_sop.UPLOAD_VERSION
    assert calls[1].args[:2] == ("POST", "/file_uploads/up-9/send")
    method, path, payload = calls[2].args
    assert (method, path) == ("PATCH", "/blocks/page-1/children")
    embed = payload["children"][0]["embed"]
    assert embed["type"] == "file_upload"
    assert embed["file_upload"] == {"id": "up-9"}
    assert embed["caption"][0]["text"]["content"] == "ROI calculator"


def test_load_api_key_prefers_env(monkeypatch):
    monkeypatch.setenv("VIDEOSKILL_NOTION_API_KEY", "ntn_test")
    assert notion_sop.load_api_key() == "ntn_test"
