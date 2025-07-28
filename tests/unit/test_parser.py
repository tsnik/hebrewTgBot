import pytest
from pathlib import Path
from bs4 import BeautifulSoup
import unicodedata

from services.parser import (
    parse_verb_page,
    parse_noun_or_adjective_page,
    parse_translations,
)

# --- Фикстуры для загрузки реального HTML ---


@pytest.fixture(scope="module")
def fixtures_path() -> Path:
    """Возвращает путь к папке с фикстурами."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def verb_paal_html(fixtures_path: Path) -> str:
    """Фикстура для глагола ПААЛЬ (lichtov)."""
    with open(fixtures_path / "1-lichtov.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def verb_piel_html(fixtures_path: Path) -> str:
    """Фикстура для глагола ПИЭЛЬ (ledaber)."""
    with open(fixtures_path / "2-ledaber.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def noun_masculine_html(fixtures_path: Path) -> str:
    """Фикстура для существительного мужского рода (kelev)."""
    with open(fixtures_path / "3483-kelev.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def noun_feminine_html(fixtures_path: Path) -> str:
    """Фикстура для существительного женского рода (mita)."""
    with open(fixtures_path / "4728-mita.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def adjective_html(fixtures_path: Path) -> str:
    """Фикстура для прилагательного (chamud)."""
    with open(fixtures_path / "5454-chamud.html", "r", encoding="utf-8") as f:
        return f.read()


# --- Основные тесты парсинга ---


def test_parse_verb_paal(verb_paal_html: str):
    """Тестирует парсинг стандартной страницы глагола (ПААЛЬ)."""
    soup = BeautifulSoup(verb_paal_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לִכְתֹּב")
    assert parsed_data["transcription"] == "лихтов"
    assert parsed_data["root"] == "כ - ת - ב"
    assert parsed_data["binyan"] == "ПААЛЬ"
    assert parsed_data["translations"][0]["translation_text"] == "писать"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_verb_piel(verb_piel_html: str):
    """Тестирует парсинг стандартной страницы глагола (ПИЭЛЬ)."""
    soup = BeautifulSoup(verb_piel_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לְדַבֵּר")
    assert parsed_data["binyan"] == "ПИЭЛЬ"
    assert parsed_data["root"] == "ד - ב - ר"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_noun_masculine(noun_masculine_html: str):
    """Тестирует парсинг страницы существительного мужского рода."""
    soup = BeautifulSoup(noun_masculine_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "noun"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "כֶּלֶב")
    assert parsed_data["gender"] == "masculine"
    assert parsed_data["singular_form"] == unicodedata.normalize("NFD", "כֶּלֶב")
    assert parsed_data["plural_form"] == unicodedata.normalize("NFD", "כְּלָבִים")


def test_parse_noun_feminine(noun_feminine_html: str):
    """Тестирует парсинг страницы существительного женского рода."""
    soup = BeautifulSoup(noun_feminine_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "noun"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "מִטָּה")
    assert parsed_data["gender"] == "feminine"
    assert parsed_data["singular_form"] == unicodedata.normalize("NFD", "מִטָּה")
    assert parsed_data["plural_form"] == unicodedata.normalize("NFD", "מִטּוֹת")


def test_parse_adjective(adjective_html: str):
    """Тестирует парсинг страницы прилагательного."""
    soup = BeautifulSoup(adjective_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_noun_or_adjective_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "adjective"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "חָמוּד")
    assert parsed_data["masculine_singular"] == unicodedata.normalize("NFD", "חָמוּד")
    assert parsed_data["feminine_singular"] == unicodedata.normalize("NFD", "חֲמוּדָה")
    assert parsed_data["masculine_plural"] == unicodedata.normalize("NFD", "חֲמוּדִים")
    assert parsed_data["feminine_plural"] == unicodedata.normalize("NFD", "חֲמוּדוֹת")


# --- Тесты на пограничные случаи ---


def test_parse_verb_page_missing_elements():
    """Тестирует парсинг глагола при отсутствии корня и биньяна."""
    html = """
    <html><body>
        <h2 class="page-header">спряжение глагола</h2>
        <div id="INF-L"><span class="menukad">לִכְתּוֹב</span></div>
        <div class="lead">to write</div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parsed_data = parse_verb_page(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["root"] is None
    assert parsed_data["binyan"] is None


def test_parser_fails_gracefully():
    """Проверяет, что парсеры возвращают None при отсутствии критических элементов."""
    # Глагол без блока инфинитива
    html_verb = (
        "<html><body><h2 class='page-header'>спряжение глагола</h2></body></html>"
    )
    soup_verb = BeautifulSoup(html_verb, "html.parser")
    assert parse_verb_page(soup_verb, soup_verb.find("h2")) is None

    # Существительное без ивритского написания
    html_noun = '<html><body><h2 class="page-header">существительное</h2><div class="lead">table</div></body></html>'
    soup_noun = BeautifulSoup(html_noun, "html.parser")
    assert parse_noun_or_adjective_page(soup_noun, soup_noun.find("h2")) is None


# --- Тесты утилиты парсинга переводов ---


def test_parse_translations_simple():
    assert parse_translations("word") == [
        {"translation_text": "word", "context_comment": None, "is_primary": True}
    ]


def test_parse_translations_multiple_simple():
    assert parse_translations("word, term") == [
        {"translation_text": "word", "context_comment": None, "is_primary": True},
        {"translation_text": "term", "context_comment": None, "is_primary": False},
    ]


def test_parse_translations_with_context():
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
    
