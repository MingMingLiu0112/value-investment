"""All native PDFium adapters share a lock, including cleanup on failure."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

import pypdfium2
import pytest

from value_investment_agent.application.product import prospective_baseline
from value_investment_agent.infrastructure.filings import official_pdf, pdf_text
from value_investment_agent.infrastructure.filings.pdfium_runtime import serialized_pdfium


def test_cross_adapter_native_lifetimes_are_serialized(tmp_path, monkeypatch):
    path = tmp_path / "TEST_ONLY.pdf"
    path.write_bytes(b"%PDF-TEST_ONLY\n%%EOF")
    state = {"active": 0, "peak": 0, "closed": 0, "calls": 0}
    guard = threading.Lock()

    class Text:
        def get_text_range(self):
            time.sleep(0.001)
            return ""

        def count_chars(self):
            return 0

        def close(self):
            assert state["active"] == 1

    class Page:
        def get_textpage(self):
            assert state["active"] == 1
            return Text()

        def close(self):
            assert state["active"] == 1

    class Document:
        def __init__(self, source):
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["calls"] += 1
            time.sleep(0.002)

        def __len__(self):
            return 1

        def __getitem__(self, index):
            assert state["active"] == 1
            return Page()

        def close(self):
            time.sleep(0.001)
            with guard:
                state["active"] -= 1
                state["closed"] += 1

    monkeypatch.setattr(pypdfium2, "PdfDocument", Document)

    def run(index):
        for _ in range(8):
            if index == 0:
                official_pdf.validate_pdf_original(path)
            elif index == 1:
                assert pdf_text.extract_pages(path, limit=1) == [""]
            else:
                with pytest.raises(ValueError, match="text and coordinate"):
                    prospective_baseline._verify_shenhua_h1_column_geometry(
                        path.read_bytes(), {"physical_page": 1})

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, range(3)))
    assert state == {"active": 0, "peak": 1, "closed": 24, "calls": 24}


def test_constructor_failure_keeps_cause_and_releases_shared_lock(tmp_path, monkeypatch, caplog):
    path = tmp_path / "TEST_ONLY.pdf"
    path.write_bytes(b"%PDF-TEST_ONLY\n%%EOF")

    class NativeFailure(Exception):
        err_code = 3

    def invalid(source):
        raise NativeFailure("TEST_ONLY original parser failure")

    monkeypatch.setattr(pypdfium2, "PdfDocument", invalid)
    with pytest.raises(ValueError, match="Official original PDF cannot be parsed") as caught:
        official_pdf.validate_pdf_original(path)
    assert isinstance(caught.value.__cause__, NativeFailure)
    assert "OFFICIAL_PDF_PARSE_FAILED exception=NativeFailure pdfium_code=3" in caplog.text
    assert str(path) not in caplog.text
    assert "TEST_ONLY original parser failure" not in caplog.text

    @serialized_pdfium
    def subsequent():
        return "LOCK_RELEASED"

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(subsequent).result(timeout=2) == "LOCK_RELEASED"


def test_new_native_pdfium_calls_require_shared_serialization():
    package = Path(__file__).resolve().parents[1] / "src/value_investment_agent"
    calls = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            native = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute) and node.func.attr == "PdfDocument"]
            if not native:
                continue
            assert any(isinstance(item, ast.Name) and item.id == "serialized_pdfium"
                       for item in function.decorator_list), (path, function.name)
            calls.extend(native)
    assert len(calls) == 3
