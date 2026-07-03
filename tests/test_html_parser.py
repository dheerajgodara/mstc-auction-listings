from scraper.html_parser import parse_html_detail

SAMPLE_HTML = """
<html><body>
<span id="ContentPlaceHolder1_lblAuctionNo">AUC/2026/JPR/001</span>
<span id="ContentPlaceHolder1_lblSellerName">Test Seller</span>
<span id="ContentPlaceHolder1_lblLocation">Jaipur</span>
<span id="ContentPlaceHolder1_dgLot_lblNo_0">1</span>
<span id="ContentPlaceHolder1_dgLot_lblName_0">EMPTY OIL DRUM</span>
<span id="ContentPlaceHolder1_dgLot_lblLotDesc_0">Scrap drums <b>as-is</b></span>
<span id="ContentPlaceHolder1_dgLot_lblQuantity_0">400.0</span>
<span id="ContentPlaceHolder1_dgLot_Label4_0">NO</span>
<span id="ContentPlaceHolder1_dgLot_sales_tax_0">/ GST 18%</span>
<span id="ContentPlaceHolder1_dgLot_lblPlace_0">Jaipur Yard</span>
<span id="ContentPlaceHolder1_dgLot_lblNo_1">2</span>
<span id="ContentPlaceHolder1_dgLot_lblName_1">STEEL PIPE</span>
<span id="ContentPlaceHolder1_dgLot_lblLotDesc_1">Used pipes</span>
<span id="ContentPlaceHolder1_dgLot_lblQuantity_1">10</span>
<span id="ContentPlaceHolder1_dgLot_Label4_1">MT</span>
<span id="ContentPlaceHolder1_dgLot_lblPlace_1">Udaipur</span>
</body></html>
"""


def test_parse_html_lots_by_index():
    data = parse_html_detail(SAMPLE_HTML)
    assert data["auction_number"] == "AUC/2026/JPR/001"
    assert data["seller"] == "Test Seller"
    assert len(data["lots"]) == 2
    assert data["lots"][0]["lot_no"] == "1"
    assert data["lots"][0]["name"] == "EMPTY OIL DRUM"
    assert "as-is" in data["lots"][0]["description"]
    assert data["lots"][0]["quantity"] == "400.0"
    assert data["lots"][0]["unit"] == "NO"
    assert data["lots"][1]["lot_no"] == "2"
    assert data["lots"][1]["name"] == "STEEL PIPE"
