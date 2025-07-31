# -*- coding: utf-8 -*-
import re
import unicodedata
from typing import Protocol, Optional, Dict, Any

from bs4 import BeautifulSoup, Tag

from config import logger
from dal.models import PartOfSpeech
from utils import parse_translations


BINYAN_HTML_MAP = {
    "пааль": "paal",
    "пиэль": "piel",
    "hифъиль": "hifil",
    "нифъаль": "nifal",
    "hитпаэль": "hitpael",
    "hифъаль": "hufal",
    "пуаль": "pual",
}


def _extract_hebrew_from_cell(cell: Tag) -> Optional[str]:
    """Извлекает только ивритскую форму из ячейки таблицы, без транскрипции."""
    if not cell:
        return None
    menukad = cell.find(class_="menukad")
    if not menukad:
        return None
    hebrew_text = menukad.text.split("~")[0].strip()
    return unicodedata.normalize("NFD", hebrew_text)


def _get_part_of_speech_from_meta(soup: BeautifulSoup) -> Optional[str]:
    """
    Извлекает часть речи из мета-тега description.
    Это наиболее надежный метод.
    """
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if not meta_tag or not meta_tag.get("content"):
        logger.warning("Мета-тег 'description' не найден или пуст.")
        return None

    content = meta_tag.get("content", "").lower()
    if content.startswith("глагол"):
        return PartOfSpeech.VERB.value
    if content.startswith("существительное"):
        return PartOfSpeech.NOUN.value
    if content.startswith("прилагательное"):
        return PartOfSpeech.ADJECTIVE.value

    logger.warning(f"Не удалось определить часть речи из мета-тега: {content[:50]}...")
    return None


def _parse_noun_forms(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Извлекает формы для существительного из таблицы.
    Сохраняет род в стандартизированном английском формате.
    """
    forms = {}
    main_header = soup.find("h2", class_="page-header")
    if main_header:
        p_tag = main_header.find_next_sibling("p")
        if p_tag:
            text = p_tag.text.lower()
            if "мужской род" in text or "masculine" in text:
                forms["gender"] = "masculine"
            elif "женский род" in text or "feminine" in text:
                forms["gender"] = "feminine"

    table = soup.find("table", class_="conjugation-table")
    if not table:
        return forms

    absolute_state_header = table.find("th", string="Абсолютное состояние")
    if absolute_state_header:
        row = absolute_state_header.parent
        cells = row.find_all("td")
        if len(cells) >= 2:
            forms["singular_form"] = _extract_hebrew_from_cell(cells[0])
            forms["plural_form"] = _extract_hebrew_from_cell(cells[1])

    return forms


def _parse_adjective_forms(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Извлекает формы для прилагательного из таблицы.
    Теперь использует _extract_hebrew_from_cell для чистоты данных.
    """
    forms = {}
    table = soup.find("table", class_="conjugation-table")
    if not table:
        return forms

    data_row = table.find("tbody").find("tr")
    if not data_row:
        return forms

    cells = data_row.find_all("td")
    if len(cells) == 4:
        forms["masculine_singular"] = _extract_hebrew_from_cell(cells[0])
        forms["feminine_singular"] = _extract_hebrew_from_cell(cells[1])
        forms["masculine_plural"] = _extract_hebrew_from_cell(cells[2])
        forms["feminine_plural"] = _extract_hebrew_from_cell(cells[3])
    return forms


class ParsingStrategy(Protocol):
    def parse(self, soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
        """Parses the page content to extract word data."""
        ...


class VerbParsingStrategy:
    def parse(self, soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
        logger.info('{{"event": "parse_verb_page_start"}}')
        try:
            data = {"part_of_speech": "verb", "is_verb": True}

            logger.debug('{{"event": "parsing_step", "step": "searching_infinitive"}}')
            infinitive_div = soup.find("div", id="INF-L")

            if not infinitive_div:
                logger.error(
                    '{{"event": "parse_verb_error", "reason": "infinitive_block_not_found"}}'
                )
                return None

            menukad_tag = infinitive_div.find("span", class_="menukad")
            if not menukad_tag:
                logger.error(
                    '{{"event": "parse_verb_error", "reason": "menukad_tag_not_found"}}'
                )
                return None

            hebrew_text = menukad_tag.text.split("~")[0].strip()
            data["hebrew"] = unicodedata.normalize("NFD", hebrew_text)
            logger.debug(
                f'{{"event": "parsing_step_success", "step": "infinitive_found", "hebrew": "{data["hebrew"]}"}}'
            )

            lead_div = soup.find("div", class_="lead")
            if not lead_div:
                logger.error(
                    f'{{"event": "parse_verb_error", "reason": "translation_div_not_found", "hebrew": "{data["hebrew"]}"}}'
                )
                return None
            data["translations"] = parse_translations(lead_div.text.strip())
            if not data["translations"]:
                logger.warning(
                    f'{{"event": "parse_verb_warning", "reason": "empty_translations", "hebrew": "{data["hebrew"]}"}}'
                )
                return None

            transcription_div = infinitive_div.find("div", class_="transcription")
            data["transcription"] = (
                transcription_div.text.strip() if transcription_div else ""
            )

            data["root"], data["binyan"] = None, None
            for p in main_header.parent.find_all("p"):
                text_lower = p.text.lower()
                if "глагол" in text_lower:
                    binyan_text = (
                        p.text.replace("Verb –", "").replace("Глагол –", "").strip()
                    )
                    binyan = binyan_text.split()[0] if binyan_text else None
                    binyan_enum_value = (
                        BINYAN_HTML_MAP.get(binyan.lower()) if binyan else None
                    )
                    if binyan_enum_value:
                        data["binyan"] = binyan_enum_value

                if "root" in text_lower or "корень" in text_lower:
                    root_tag = p.find("span", class_="menukad")
                    if root_tag:
                        data["root"] = root_tag.text.strip()

            logger.debug(
                f'{{"event": "parsing_step_success", "step": "root_and_binyan_parsed", "root": "{data["root"]}", "binyan": "{data["binyan"]}"}}'
            )

            conjugations = []
            verb_forms = soup.find_all(
                "div", id=re.compile(r"^(AP|PERF|IMPF|IMP|INF)-")
            )
            for form in verb_forms:
                form_id, menukad_tag, trans_tag = (
                    form.get("id"),
                    form.find("span", class_="menukad"),
                    form.find("div", class_="transcription"),
                )
                if all([form_id, menukad_tag, trans_tag]):
                    tense_prefix = form_id.split("-")[0].lower()
                    person = (
                        form_id.split("-")[1]
                        if len(form_id.split("-")) > 1
                        else "форма"
                    )
                    conjugations.append(
                        {
                            "tense": tense_prefix,
                            "person": person,
                            "hebrew_form": menukad_tag.text.strip()
                            .split("~")[0]
                            .strip(),
                            "transcription": trans_tag.text.strip(),
                        }
                    )
            data["conjugations"] = conjugations

            logger.info(
                f'{{"event": "parse_verb_page_success", "found_conjugations": {len(conjugations)}}}'
            )
            return data
        except Exception as e:
            logger.error(
                f'{{"event": "parse_verb_page_exception", "error": "{e}"}}',
                exc_info=True,
            )
            return None


class NounAdjectiveParsingStrategy:
    def parse(self, soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
        part_of_speech = _get_part_of_speech_from_meta(soup)
        if not part_of_speech or part_of_speech == "verb":
            logger.error(
                f'{{"event": "wrong_parser_error", "part_of_speech": "{part_of_speech}"}}'
            )
            return None

        logger.info(
            f'{{"event": "parse_noun_adj_start", "part_of_speech": "{part_of_speech}"}}'
        )
        try:
            data = {
                "root": None,
                "binyan": None,
                "conjugations": [],
                "part_of_speech": part_of_speech,
                "is_verb": False,
            }

            logger.debug(
                '{{"event": "parsing_step", "step": "searching_canonical_form"}}'
            )
            canonical_hebrew = None
            table = soup.find("table", class_="conjugation-table")

            if table:
                if part_of_speech == "noun":
                    header_cell = table.find("th", string="Абсолютное состояние")
                    if header_cell:
                        data_cell = header_cell.parent.find("td")
                        if data_cell:
                            canonical_hebrew = _extract_hebrew_from_cell(data_cell)
                elif part_of_speech == "adjective":
                    data_cell = table.find("td")
                    if data_cell:
                        canonical_hebrew = _extract_hebrew_from_cell(data_cell)

            if not canonical_hebrew:
                logger.error(
                    '{{"event": "parse_noun_adj_error", "reason": "canonical_form_not_found"}}'
                )
                return None

            data["hebrew"] = canonical_hebrew
            logger.debug(
                f'{{"event": "parsing_step_success", "step": "canonical_form_found", "hebrew": "{data["hebrew"]}"}}'
            )

            lead_div = soup.find("div", class_="lead")
            if not lead_div:
                logger.error(
                    f'{{"event": "parse_noun_adj_error", "reason": "translation_div_not_found", "hebrew": "{data["hebrew"]}"}}'
                )
                return None

            data["translations"] = parse_translations(lead_div.text.strip())
            if not data["translations"]:
                logger.warning(
                    f'{{"event": "parse_noun_adj_warning", "reason": "empty_translations", "hebrew": "{data["hebrew"]}"}}'
                )
                return None

            first_form = soup.find("div", class_="transcription")
            data["transcription"] = first_form.text.strip() if first_form else ""

            if data["part_of_speech"] == "noun":
                forms = _parse_noun_forms(soup)
                data.update(forms)
            elif data["part_of_speech"] == "adjective":
                forms = _parse_adjective_forms(soup)
                data.update(forms)

            logger.info(
                f'{{"event": "parse_noun_adj_success", "hebrew": "{data["hebrew"]}"}}'
            )
            return data
        except Exception as e:
            logger.error(
                f'{{"event": "parse_noun_adj_exception", "error": "{e}"}}',
                exc_info=True,
            )
            return None


def get_parsing_strategy(part_of_speech: str) -> Optional[ParsingStrategy]:
    """Factory function to get the appropriate parsing strategy."""
    strategies = {
        PartOfSpeech.VERB.value: VerbParsingStrategy(),
        PartOfSpeech.NOUN.value: NounAdjectiveParsingStrategy(),
        PartOfSpeech.ADJECTIVE.value: NounAdjectiveParsingStrategy(),
    }
    return strategies.get(part_of_speech)
