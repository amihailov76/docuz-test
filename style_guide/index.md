# Стайлгайд: индекс разделов

Этот стайлгайд описывает правила написания технической документации на русском языке.

## Разделы

| Файл | Раздел | Краткое содержание |
|------|--------|--------------------|
| [01_instructions.md](01_instructions.md) | Инструкции | Как писать инструкции: структура, заголовки, шаги |
| [02_neutral_tone.md](02_neutral_tone.md) | Нейтральный тон | Что запрещено: оценочные слова, этикет, антропоморфизм |
| [03_word_choice.md](03_word_choice.md) | Выбор слов | Пустые слова, оговорки, усиления, авторская речь |
| [04_sentences.md](04_sentences.md) | Абзацы и предложения | Порядок слов, залог, структура предложений |
| [05_links.md](05_links.md) | Ссылки, сноски, подсказки | Гиперссылки, перекрёстные ссылки, сноски |

## Использование в MCP-сервере

Каждый раздел доступен через отдельный endpoint:

```
GET /tools/get_style_guide?section=instructions
GET /tools/get_style_guide?section=neutral_tone
GET /tools/get_style_guide?section=word_choice
GET /tools/get_style_guide?section=sentences
GET /tools/get_style_guide?section=links
GET /tools/get_style_guide          # возвращает все разделы
```
