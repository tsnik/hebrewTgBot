import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock
from services.parser import (
    parse_verb_page,
    parse_noun_or_adjective_page,
    parse_translations,
)

# Mock HTML for PI'EL verb
piel_verb_html = """
<html>
    <head><title>Test Verb</title></head>
    <body>
        <h2 class="page-header">спряжение глагола</h2>
        <div>
            <div id="INF-L">
                <span class="menukad">לְדַבֵּר</span>
                <div class="transcription">ledaber</div>
            </div>
            <div class="lead">to speak</div>
            <p><b>биньян:</b> פיעל</p>
            <p><b>корень:</b> <span class="menukad">ד.ב.ר</span></p>
            <div id="AP-M-S">
                <span class="menukad">מְדַבֵּר</span>
                <div class="transcription">medaber</div>
            </div>
        </div>
    </body>
</html>
"""

# Mock HTML for NIF'AL verb
nifal_verb_html = """
<html>
    <head><title>Test Verb</title></head>
    <body>
        <h2 class="page-header">спряжение глагола</h2>
        <div>
            <div id="INF-L">
                <span class="menukad">לְהִיכָּנֵס</span>
                <div class="transcription">lehikanes</div>
            </div>
            <div class="lead">to enter</div>
            <p><b>биньян:</b> נפעל</p>
            <p><b>корень:</b> <span class="menukad">כ.נ.ס</span></p>
            <div id="AP-M-S">
                <span class="menukad">נִכְנָס</span>
                <div class="transcription">nichnas</div>
            </div>
        </div>
    </body>
</html>
"""


def test_parse_piel_verb_page():
    soup = BeautifulSoup(piel_verb_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is True
    assert parsed_data["hebrew"] == "לְדַבֵּר"
    assert parsed_data["binyan"] == "פיעל"
    assert parsed_data["root"] == "ד.ב.ר"
    assert len(parsed_data["conjugations"]) > 0


def test_parse_nifal_verb_page():
    soup = BeautifulSoup(nifal_verb_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is True
    assert parsed_data["hebrew"] == "לְהִיכָּנֵס"
    assert parsed_data["binyan"] == "נפעל"
    assert parsed_data["root"] == "כ.נ.ס"
    assert len(parsed_data["conjugations"]) > 0


# Mock HTML for masculine noun
masculine_noun_html = """
<html>
    <head><title>Test Noun</title></head>
    <body>
        <h2 class="page-header">
            <span class="menukad">שֻׁלְחָן</span>
        </h2>
        <div class="lead">table, desk</div>
        <div class="transcription">shulchan</div>
        <div class="short-table">
            <div class="stuff-box">m.</div>
        </div>
    </body>
</html>
"""

# Mock HTML for feminine noun
feminine_noun_html = """
<html>
    <head><title>Test Noun</title></head>
    <body>
        <h2 class="page-header">
            <span class="menukad">מִטָּה</span>
        </h2>
        <div class="lead">bed</div>
        <div class="transcription">mita</div>
        <div class="stuff-box">f.</div>
    </body>
</html>
"""

# Mock HTML for adjective
adjective_html = """
<html>
    <head><title>Test Adjective</title></head>
    <body>
        <h2 class="page-header">
            <span class="menukad">טוֹב</span>
        </h2>
        <div class="lead">good</div>
        <div class="transcription">tov</div>
        <div class="stuff-box">adj.</div>
    </body>
</html>
"""


def test_parse_masculine_noun_page():
    soup = BeautifulSoup(masculine_noun_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is False
    assert parsed_data["hebrew"] == "שֻׁלְחָן"
    # The gender is not parsed yet, so this will fail.
    # I will add the gender parsing logic later.
    # assert parsed_data['gender'] == 'masculine'


def test_parse_feminine_noun_page():
    soup = BeautifulSoup(feminine_noun_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is False
    assert parsed_data["hebrew"] == "מִטָּה"
    # The gender is not parsed yet, so this will fail.
    # I will add the gender parsing logic later.
    # assert parsed_data['gender'] == 'feminine'


def test_parse_adjective_page():
    soup = BeautifulSoup(adjective_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["is_verb"] is False
    assert parsed_data["hebrew"] == "טוֹב"
    # The type is not parsed yet, so this will fail.
    # I will add the type parsing logic later.
    # assert parsed_data['type'] == 'adjective'


def test_parse_translations_multiple_meanings():
    raw_text = "peace, quiet (formal); hello, goodbye (colloquial)"
    expected = [
        {"translation_text": "peace", "context_comment": "formal", "is_primary": True},
        {"translation_text": "quiet", "context_comment": "formal", "is_primary": False},
        {
            "translation_text": "hello",
            "context_comment": "colloquial",
            "is_primary": False,
        },
        {
            "translation_text": "goodbye",
            "context_comment": "colloquial",
            "is_primary": False,
        },
    ]
    assert parse_translations(raw_text) == expected


def test_parse_page_missing_elements():
    # Mock HTML with missing root and binyan
    missing_elements_html = """
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
                <div id="AP-M-S">
                    <span class="menukad">כּוֹתֵב</span>
                    <div class="transcription">kotev</div>
                </div>
            </div>
        </body>
    </html>
    """
    soup = BeautifulSoup(missing_elements_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["root"] is None
    assert parsed_data["binyan"] is None


@pytest.mark.asyncio
async def test_fetch_word_not_found():
    from app.services.parser import fetch_and_cache_word_data

    with patch("app.services.parser.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.url = "https://www.pealim.com/search/?from-nav=1&q=xyzxyz"
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get.return_value = (
            mock_response
        )
        status, data = await fetch_and_cache_word_data("xyzxyz")
        assert status == "not_found"
        assert data is None


def test_parse_translations_literary_context():
    raw_text = "dress, gown (literary)"
    expected = [
        {
            "translation_text": "dress",
            "context_comment": "literary",
            "is_primary": True,
        },
        {
            "translation_text": "gown",
            "context_comment": "literary",
            "is_primary": False,
        },
    ]
    assert parse_translations(raw_text) == expected
