from unittest.mock import patch

from scraper.models import AuctionRecord, AuctionsExport, LotRecord
from scraper.run_all import run_all


@patch("scraper.run_all.run_mstc_source")
def test_run_all_mstc_only(mock_mstc):
    mock_mstc.return_value = (
        [
            AuctionRecord(
                id="1",
                auction_number="1",
                source="mstc",
                source_auction_id="1",
                region="JPR",
                office="JPR",
                lots=[LotRecord(lot_id="1", item_title="Lot")],
            )
        ],
        {"documents": {}},
    )
    export = run_all(
        sources=["mstc"],
        out_path=__import__("pathlib").Path("work/test_run_all_mstc.json"),
        pdf_dir=__import__("pathlib").Path("web/public/pdfs"),
        docs_dir=__import__("pathlib").Path("web/public/docs"),
        thumbs_dir=__import__("pathlib").Path("web/public/thumbs"),
        limit=5,
    )
    assert export.count == 1
    assert export.stats["by_source"]["mstc"] == 1


@patch("scraper.run_all.run_eauction_source")
@patch("scraper.run_all.run_mstc_source")
def test_run_all_continues_when_optional_source_fails(mock_mstc, mock_ea):
    mock_mstc.return_value = (
        [
            AuctionRecord(
                id="1",
                auction_number="1",
                source="mstc",
                source_auction_id="1",
                region="JPR",
                office="JPR",
                lots=[],
            )
        ],
        {},
    )
    mock_ea.return_value = ([], {"error": "blocked"})
    export = run_all(
        sources=["mstc", "eauction"],
        out_path=__import__("pathlib").Path("work/test_run_all_mstc.json"),
        pdf_dir=__import__("pathlib").Path("web/public/pdfs"),
        docs_dir=__import__("pathlib").Path("web/public/docs"),
        thumbs_dir=__import__("pathlib").Path("web/public/thumbs"),
    )
    assert export.count == 1
    assert "eauction" in export.stats["failures_by_source"]


@patch("scraper.run_all.run_eauction_source")
def test_run_all_eauction_only_success(mock_ea):
    mock_ea.return_value = (
        [
            AuctionRecord(
                id="eauction:90001",
                source="eauction",
                source_auction_id="90001",
                auction_number="90001",
                region="eAuction",
                office="Test Org",
                seller="Test Org",
                closing=__import__("datetime").datetime(2026, 7, 5, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata")),
                detail_url="https://eauction.gov.in/view",
                lots=[LotRecord(lot_id="1", item_title="Iron Scrap")],
            )
        ],
        {"status": "ok", "detail_success": 1, "detail_fail": 0},
    )
    export = run_all(
        sources=["eauction"],
        out_path=__import__("pathlib").Path("work/test_eauction_export.json"),
        pdf_dir=__import__("pathlib").Path("web/public/pdfs"),
        docs_dir=__import__("pathlib").Path("web/public/docs"),
        thumbs_dir=__import__("pathlib").Path("web/public/thumbs"),
        eauction_limit=50,
    )
    assert export.count == 1
    assert export.stats["by_source"]["eauction"] == 1
    mock_ea.assert_called_once()
    assert mock_ea.call_args.kwargs["limit"] == 50


@patch("scraper.run_all.run_eauction_source")
@patch("scraper.run_all.run_mstc_source")
def test_run_all_per_source_limits(mock_mstc, mock_ea):
    mock_mstc.return_value = ([], {})
    mock_ea.return_value = ([], {"status": "ok"})
    run_all(
        sources=["mstc", "eauction"],
        out_path=__import__("pathlib").Path("work/test_limits.json"),
        pdf_dir=__import__("pathlib").Path("web/public/pdfs"),
        docs_dir=__import__("pathlib").Path("web/public/docs"),
        thumbs_dir=__import__("pathlib").Path("web/public/thumbs"),
        mstc_limit=300,
        eauction_limit=50,
    )
    mock_mstc.assert_called_once()
    assert mock_mstc.call_args.kwargs["limit"] == 300
    mock_ea.assert_called_once()
    assert mock_ea.call_args.kwargs["limit"] == 50
