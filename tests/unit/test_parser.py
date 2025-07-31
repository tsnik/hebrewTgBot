import pytest
from pathlib import Path
from bs4 import BeautifulSoup
import unicodedata

from services.parsing_strategies import (
    VerbParsingStrategy,
    NounAdjectiveParsingStrategy,
)
from utils import parse_translations

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
def verb_hifil_html(fixtures_path: Path) -> str:
    """Фикстура для глагола hИФЪИЛЬ (lehargish)."""
    # Используем предоставленный файл 1993-lehargish.html
    with open(fixtures_path / "1993-lehargish.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def verb_nifal_html(fixtures_path: Path) -> str:
    """Фикстура для глагола НИФЪАЛЬ (lehipagesh)."""
    # Используем предоставленный файл 1593-lehipagesh.html
    with open(fixtures_path / "1593-lehipagesh.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def verb_hitpael_html(fixtures_path: Path) -> str:
    """Фикстура для глагола hИТПАЭЛЬ (lehitpalel)."""
    # Используем предоставленный файл 2435-lehitpael.html
    with open(fixtures_path / "2435-lehitpael.html", "r", encoding="utf-8") as f:
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
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לִכְתֹּב")
    assert parsed_data["transcription"] == "лихтов"
    assert parsed_data["root"] == "כ - ת - ב"
    assert parsed_data["binyan"] == "paal"
    assert parsed_data["translations"][0]["translation_text"] == "писать"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_verb_piel(verb_piel_html: str):
    """Тестирует парсинг стандартной страницы глагола (ПИЭЛЬ)."""
    soup = BeautifulSoup(verb_piel_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לְדַבֵּר")
    assert parsed_data["binyan"] == "piel"
    assert parsed_data["root"] == "ד - ב - ר"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_verb_hifil(verb_hifil_html: str):
    """Тестирует парсинг страницы глагола (hИФЪИЛЬ)."""
    soup = BeautifulSoup(verb_hifil_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לְהַרְגִּישׁ")
    assert parsed_data["transcription"] == "леhаргиш"
    assert parsed_data["root"] == "ר - ג - שׁ"
    assert parsed_data["binyan"] == "hifil"  # Проверяем маппинг
    assert parsed_data["translations"][0]["translation_text"] == "чувствовать"
    assert parsed_data["translations"][1]["translation_text"] == "чувствовать себя"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_verb_nifal(verb_nifal_html: str):
    """Тестирует парсинг страницы глагола (НИФЪАЛЬ)."""
    soup = BeautifulSoup(verb_nifal_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    # На странице есть альтернативное написание, парсер должен брать первое
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לְהִפָּגֵשׁ")
    assert parsed_data["transcription"] == "леhипагеш"
    assert parsed_data["root"] == "פ - ג - שׁ"
    assert parsed_data["binyan"] == "nifal"  # Проверяем маппинг
    assert parsed_data["translations"][0]["translation_text"] == "встретиться"
    assert parsed_data["translations"][0]["context_comment"] == "в т. ч. случайно"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_verb_hitpael(verb_hitpael_html: str):
    """Тестирует парсинг страницы глагола (hИТПАЭЛЬ)."""
    soup = BeautifulSoup(verb_hitpael_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

    assert parsed_data is not None
    assert parsed_data["part_of_speech"] == "verb"
    assert parsed_data["hebrew"] == unicodedata.normalize("NFD", "לְהִתְפַּלֵּל")
    assert parsed_data["transcription"] == "леhитпалель"
    assert parsed_data["root"] == "פ - ל - ל"
    assert parsed_data["binyan"] == "hitpael"  # Проверяем маппинг
    assert parsed_data["translations"][0]["translation_text"] == "молиться"
    assert len(parsed_data["conjugations"]) > 1


def test_parse_noun_masculine(noun_masculine_html: str):
    """Тестирует парсинг страницы существительного мужского рода."""
    soup = BeautifulSoup(noun_masculine_html, "html.parser")
    main_header = soup.find("h2", class_="page-header")
    parser = NounAdjectiveParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

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
    parser = NounAdjectiveParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

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
    parser = NounAdjectiveParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

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
    parser = VerbParsingStrategy()
    parsed_data = parser.parse(soup, main_header)

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
    parser_verb = VerbParsingStrategy()
    assert parser_verb.parse(soup_verb, soup_verb.find("h2")) is None

    # Существительное без ивритского написания
    html_noun = '<html><body><h2 class="page-header">существительное</h2><div class="lead">table</div></body></html>'
    soup_noun = BeautifulSoup(html_noun, "html.parser")
    parser_noun = NounAdjectiveParsingStrategy()
    assert parser_noun.parse(soup_noun, soup_noun.find("h2")) is None


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
