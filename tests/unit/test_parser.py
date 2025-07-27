import pytest
from bs4 import BeautifulSoup
from services.parser import parse_verb_page, parse_noun_or_adjective_page

# Mock HTML for verb page
verb_html = """
<html>
    <head><title>Test Verb</title></head>
    <body>
        <h2 class="page-header">спряжение глагола</h2>
        <div>
            <div id="INF-L">
                <span class="menukad">לִכְתּוֹב</span>
                <div class="transcription">likhtov</div>
            </div>
            <div class="lead">to write</div>
            <p><b>биньян:</b> פעל</p>
            <p><b>корень:</b> <span class="menukad">כ-ת-ב</span></p>
            <div id="AP-M-S">
                <span class="menukad">כּוֹתֵב</span>
                <div class="transcription">kotev</div>
            </div>
        </div>
    </body>
</html>
"""

# Mock HTML for noun page
noun_html = """
<html>
    <head><title>Test Noun</title></head>
    <body>
        <h2 class="page-header">
            <span class="menukad">שֻׁלְחָן</span>
        </h2>
        <div class="lead">table, desk</div>
        <div class="transcription">shulchan</div>
    </body>
</html>
"""


def test_parse_verb_page():
    soup = BeautifulSoup(verb_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is True
    assert parsed_data["hebrew"] == "לִכְתּוֹב"
    assert parsed_data["transcription"] == "likhtov"
    assert parsed_data["root"] == "כ-ת-ב"
    assert parsed_data["binyan"] == "פעל"
    assert len(parsed_data["translations"]) == 1
    assert parsed_data["translations"][0]["translation_text"] == "to write"
    assert len(parsed_data["conjugations"]) == 2
    assert parsed_data["conjugations"][0]["hebrew_form"] == "לִכְתּוֹב"
    assert parsed_data["conjugations"][1]["hebrew_form"] == "כּוֹתֵב"


def test_parse_noun_or_adjective_page():
    soup = BeautifulSoup(noun_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is False
    assert parsed_data["hebrew"] == "שֻׁלְחָן"
    assert parsed_data["transcription"] == "shulchan"
    assert len(parsed_data["translations"]) == 2
    assert parsed_data["translations"][0]["translation_text"] == "table"
    assert parsed_data["translations"][1]["translation_text"] == "desk"


def test_parse_verb_page_no_infinitive_div():
    html = "<html><body><h2 class='page-header'>спряжение глагола</h2></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    assert parse_verb_page(soup, main_header) is None


def test_parse_verb_page_no_menukad_in_infinitive():
    html = """
    <html><body><h2 class="page-header">спряжение глагола</h2>
    <div id="INF-L"><div class="transcription">likhtov</div></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    assert parse_verb_page(soup, main_header) is None


def test_parse_verb_page_no_lead_div():
    html = """
    <html><body><h2 class="page-header">спряжение глагола</h2>
    <div id="INF-L"><span class="menukad">לִכְתּוֹב</span><div class="transcription">likhtov</div></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    assert parse_verb_page(soup, main_header) is None


def test_parse_verb_page_no_root_or_binyan():
    soup = BeautifulSoup(verb_html, "html.parser")
    # Intentionally remove root and binyan paragraphs
    for p in soup.find_all("p"):
        p.decompose()
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)
    assert parsed_data is not None
    assert parsed_data["root"] is None
    assert parsed_data["binyan"] is None


def test_parse_verb_page_no_conjugations():
    html = """
    <html>
        <head><title>Test Verb No Conjugations</title></head>
        <body>
            <h2 class="page-header">спряжение глагола</h2>
            <div>
                <div id="INF-L">
                    <span class="menukad">לִכְתּוֹב</span>
                    <div class="transcription">likhtov</div>
                </div>
                <div class="lead">to write</div>
                <p><b>биньян:</b> פעל</p>
                <p><b>корень:</b> <span class="menukad">כ-ת-ב</span></p>
            </div>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)
    assert parsed_data is not None
    assert len(parsed_data["conjugations"]) == 1  # Only infinitive


def test_parse_noun_or_adjective_page_no_menukad():
    html = """
    <html><head><title>Test Noun</title></head>
    <body><h2 class="page-header"></h2><div class="lead">table, desk</div>
    <div class="transcription">shulchan</div></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)
    assert parsed_data is None


def test_parse_noun_or_adjective_page_no_lead_div():
    html = """
    <html><head><title>Test Noun</title></head>
    <body><h2 class="page-header"><span class="menukad">שֻׁלְחָן</span></h2>
    <div class="transcription">shulchan</div></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)
    assert parsed_data is None
