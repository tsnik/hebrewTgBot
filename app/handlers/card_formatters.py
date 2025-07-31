# -*- coding: utf-8 -*-

from typing import Protocol

from config import BINYAN_MAP
from dal.models import CachedWord, PartOfSpeech


class CardFormattingStrategy(Protocol):
    def format(self, word_data: CachedWord) -> str:
        """Formats the word data into a string for the card."""
        ...


class VerbCardFormatter:
    def format(self, word_data: CachedWord) -> str:
        card_text = ""
        if word_data.root:
            card_text += f"\nКорень: {word_data.root}"
        if word_data.binyan:
            display_binyan = BINYAN_MAP.get(
                word_data.binyan.value, word_data.binyan.value
            ).capitalize()
            card_text += f"\nБиньян: {display_binyan}"
        return card_text


class NounCardFormatter:
    def format(self, word_data: CachedWord) -> str:
        card_text = ""
        if word_data.gender:
            gender_display = (
                "Мужской род" if word_data.gender == "masculine" else "Женский род"
            )
            card_text += f"\nРод: {gender_display}"
        if word_data.singular_form:
            card_text += f"\nЕд. число: {word_data.singular_form}"
        if word_data.plural_form:
            card_text += f"\nМн. число: {word_data.plural_form}"
        return card_text


class AdjectiveCardFormatter:
    def format(self, word_data: CachedWord) -> str:
        card_text = "\n*Формы:*"
        if word_data.masculine_singular:
            card_text += f"\nм.р., ед.ч.: {word_data.masculine_singular}"
        if word_data.feminine_singular:
            card_text += f"\nж.р., ед.ч.: {word_data.feminine_singular}"
        if word_data.masculine_plural:
            card_text += f"\nм.р., мн.ч.: {word_data.masculine_plural}"
        if word_data.feminine_plural:
            card_text += f"\nж.р., мн.ч.: {word_data.feminine_plural}"
        return card_text


def get_card_formatter(
    part_of_speech: PartOfSpeech,
) -> CardFormattingStrategy:
    """Factory to get card formatter based on part of speech."""
    formatters = {
        PartOfSpeech.VERB: VerbCardFormatter(),
        PartOfSpeech.NOUN: NounCardFormatter(),
        PartOfSpeech.ADJECTIVE: AdjectiveCardFormatter(),
    }
    return formatters.get(part_of_speech)
