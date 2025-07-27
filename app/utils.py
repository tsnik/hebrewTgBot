# -*- coding: utf-8 -*-

import re
from typing import List, Dict, Any


def normalize_hebrew(text: str) -> str:
    """
    Нормализует текст на иврите: удаляет огласовки (никуд) и
    приводит к базовой форме написания.
    """
    if not text:
        return ""
    # Удаление всех огласовок (U+0591 до U+05C7)
    text = re.sub(r"[\u0591-\u05C7]", "", text)
    # Базовые правила унификации (можно расширять)
    # text = text.replace('יי', 'י')
    # text = text.replace('וו', 'ו')
    return text.strip()


def parse_translations(raw_text: str) -> List[Dict[str, Any]]:
    """
    Принимает сырую строку из div.lead и преобразует ее в
    структурированный список переводов.
    """
    all_translations = []
    if not raw_text:
        return []

    # Разделение по точкам с запятой для основных групп переводов
    major_groups = [group.strip() for group in raw_text.split(";")]

    for group_text in major_groups:
        # Поиск комментария в скобках
        comment_match = re.search(r"\((.*?)\)", group_text)
        comment = comment_match.group(1).strip() if comment_match else None

        # Удаление комментария из строки для дальнейшего парсинга
        clean_group_text = re.sub(r"\s*\((.*?)\)", "", group_text).strip()

        # Разделение по запятым для второстепенных переводов
        minor_translations = [t.strip() for t in clean_group_text.split(",")]

        for translation_text in minor_translations:
            if translation_text:
                all_translations.append(
                    {
                        "translation_text": translation_text,
                        "context_comment": comment,
                        "is_primary": False,  # По умолчанию все не основные
                    }
                )

    # Первое значение в списке считается основным
    if all_translations:
        all_translations[0]["is_primary"] = True

    return all_translations
