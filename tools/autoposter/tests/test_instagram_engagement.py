from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engagement.comment import draft_comments  # noqa: E402
from src.engagement.dm import prepare_dm  # noqa: E402
from src.engagement.pipeline import build_engagement_drafts, is_enabled  # noqa: E402
from src.engagement.reply import classify_comments  # noqa: E402


class CommentTests(unittest.TestCase):
    def test_two_specific_safe_drafts_without_invented_experience(self) -> None:
        result = draft_comments("BPW ECO Meter считает пробег прицепа независимо от тягача.", "bpw")
        self.assertEqual(len(result["drafts"]), 2)
        self.assertEqual(len({row["type"] for row in result["drafts"]}), 2)
        joined = " ".join(row["text"] for row in result["drafts"])
        self.assertIn("BPW ECO Meter", joined)
        self.assertNotRegex(joined.lower(), r"мы (использовали|проверили|ездили)|https?://")
        self.assertFalse(result["auto_posted"])

    def test_unsupported_context_is_warning_not_fact(self) -> None:
        result = draft_comments("Новая ось рассчитана для городских перевозок.", "maker", {"fact": "Грузоподъёмность 20 тонн.", "evidence": "Новая ось предназначена для города."})
        self.assertEqual(result["warnings"][0]["code"], "unsupported_verified_context")
        self.assertNotIn("20 тонн", " ".join(x["text"] for x in result["drafts"]))

    def test_missing_context_requires_review(self) -> None:
        self.assertEqual(draft_comments("Коротко", "")["status"], "editorial_review_required")


class ReplyTests(unittest.TestCase):
    def test_categories_spam_hostility_and_unanswered_question(self) -> None:
        comments = [
            {"handle": "@a", "text": "ЧЕК-ЛИСТ"},
            {"handle": "@b", "text": "Сколько стоит подбор тягача?"},
            {"handle": "@c", "text": "Не согласен: на региональных маршрутах расход зависит от загрузки."},
            {"handle": "@d", "text": "Как проверить пробег прицепа?"},
            {"handle": "@e", "text": "Спасибо"},
            {"handle": "@f", "text": "Ты тупой, подпишись на меня https://spam.test"},
        ]
        result = classify_comments(comments, keyword="чек-лист")
        self.assertEqual(result["counts"], {name: 1 for name in ("KEYWORD", "LEAD", "SUBSTANCE", "QUESTION", "SUPPORT", "NOISE")})
        self.assertEqual(result["status"], "editorial_review_required")
        self.assertEqual({x["reason"] for x in result["skipped"]}, {"low_value_support", "spam_or_hostility"})
        self.assertFalse(result["auto_replied"])

    def test_verified_answer_is_used_without_invention(self) -> None:
        question = "Где установлен счётчик?"
        answer = "По документации BPW счётчик встроен в крышку ступицы."
        result = classify_comments([{"handle": "@fleet", "text": question}], verified_answers={question: answer})
        self.assertEqual(result["prioritized_replies"][0]["reply"], answer)
        self.assertEqual(result["status"], "draft_ready")


class DmTests(unittest.TestCase):
    def test_resource_request_and_no_auto_send(self) -> None:
        result = prepare_dm({"kind": "resource_request", "handle": "fleet", "name": "Иван", "trigger": "попросил чек-лист в комментарии", "contact_reason": "предрейсовая проверка", "resource": "https://example.test/checklist"})
        self.assertEqual(result["status"], "draft_ready")
        self.assertEqual(result["character_count"], len(result["message"]))
        self.assertFalse(result["sent"])

    def test_missing_or_generic_outreach_context_is_rejected(self) -> None:
        result = prepare_dm({"kind": "partnership", "handle": "brand", "contact_reason": "подходит аудитория"})
        self.assertEqual(result["status"], "editorial_review_required")
        self.assertEqual(result["message"], "")

    def test_specific_partnership_has_at_most_two_followups(self) -> None:
        result = prepare_dm({"kind": "partnership", "handle": "trailer_maker", "trigger": "ваш пост о новой оси", "contact_reason": "совместный технический разбор", "proposal": "Предлагаем совместный пост о регламенте оси.", "recipient_benefit": "вы проверяете технические формулировки до публикации", "ask": "Готовы обсудить структуру?", "follow_up_value": "пришлём черновой план без обязательств"})
        self.assertEqual(result["status"], "draft_ready")
        self.assertLessEqual(len(result["follow_ups"]), 2)


class IsolationTests(unittest.TestCase):
    def test_disabled_by_default_and_returns_no_drafts(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_enabled())
            result = build_engagement_drafts(comment_request={}, imported_comments=[], dm_request={})
        self.assertEqual(result["status"], "disabled")
        self.assertIsNone(result["comments"])
        self.assertFalse(result["dm_sent"])
        self.assertFalse(result["network_accessed"])


if __name__ == "__main__":
    unittest.main()
