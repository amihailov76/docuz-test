# Сценарий демо

## Структура файлов

```
docs/ru/choose-configuration.mdx   ← чистая версия (на main, без нарушений)
docs/en/choose-configuration.mdx   ← чистая версия (на main, без нарушений)

demo/ru/choose-configuration.mdx   ← версия с нарушениями (источник для демо)
demo/en/choose-configuration.mdx   ← версия с нарушениями (источник для демо)
```

Папка `demo/` хранится на `main` и никогда не удаляется. При сбросе скрипт
копирует файлы из `demo/` в `docs/` — тестовые файлы с нарушениями всегда
на месте.

---

## Внесённые нарушения

### docs/ru/choose-configuration.mdx (демо-версия)

| # | Строка | Нарушение | Правило | Подсказка |
|---|--------|-----------|---------|-----------|
| 1 | 14 | `Как правило` | WordChoice — слово-паразит | обычно |
| 2 | 14 | `В большинстве случаев` | WordChoice — размытая формулировка | конкретизировать |
| 3 | 14 | `вы должны` | Substitutions — директивная конструкция | вам нужно |
| 4 | 18 | `эффективную` | WordChoice — маркетинговое прилагательное | опишите конкретную характеристику |
| 5 | 22 | `Необходимо` | Substitutions — директивная конструкция | нужно |
| 6 | 24 | `осуществляет анализ` | WordChoice — канцелярит | анализирует |

Нарушение для LLM-агента (линтер не видит): строка 14 — одно предложение
содержит три утверждения, нарушение принципа «одна мысль — одно предложение».

### docs/en/choose-configuration.mdx (демо-версия)

| # | Строка | Нарушение | Правило |
|---|--------|-----------|---------|
| 1 | 14 | `very` | Microsoft.Adverbs |
| 2 | 14 | `easily` | Microsoft.Adverbs |
| 3 | 26 | `can be added` | Microsoft.Passive |
| 4 | 21, 25, 28 | пропущена Oxford comma | Microsoft.OxfordComma |

---

## Этап 0. Подготовка main — один раз

Выполняется один раз. Фиксирует чистые версии файлов и папку `demo/` на `main`.

```bash
cd C:\docuz-test
git checkout main

git add docs/ru/choose-configuration.mdx
git add docs/en/choose-configuration.mdx
git add demo/
git add DEMO.md
git commit -m "demo: add clean docs pages and demo source files"
git push
```

После этого шага `main` содержит:
- чистые версии файлов в `docs/`
- версии с нарушениями в `demo/`

---

## Этап 1. Первый запуск демо

Создать демо-ветку: скопировать файлы с нарушениями поверх чистых и запушить.

```bash
cd C:\docuz-test
git checkout main
git pull
git checkout -b demo/choose-configuration

copy demo\ru\choose-configuration.mdx docs\ru\choose-configuration.mdx
copy demo\en\choose-configuration.mdx docs\en\choose-configuration.mdx

git add docs/ru/choose-configuration.mdx docs/en/choose-configuration.mdx
git commit -m "docs: choose-configuration page (RU + EN)"
git push -u origin demo/choose-configuration
```

---

## Этап 2. Открыть Pull Request

Перейти по ссылке:
```
https://github.com/amihailov76/docuz-test/compare/demo/choose-configuration
```

Нажать **Create pull request**. Заголовок: `Add choose-configuration page`.

В PR видны два изменённых файла с нарушениями как diff.

---

## Этап 3. Запустить проверку

В PR справа нажать **Labels → docs-review**.

Перейти во вкладку **Checks** — наблюдать за шагами воркфлоу:

- `Fetch rules and style guide` — получение правил
- `Lint Russian files (Python)` — 6 нарушений с номерами строк и подсказками
- `Lint English files (Vale)` — нарушения Microsoft + proselint
- `Run LLM review agent` — LLM анализирует оба файла со стайлгайдом

Результат: inline-комментарии в PR во вкладке **Files changed**.

---

## Этап 4. Сброс для повторного прогона

Закрыть PR на GitHub (кнопка **Close pull request**), затем:

```bash
cd C:\docuz-test
git checkout main

git push origin --delete demo/choose-configuration
git branch -D demo/choose-configuration

git checkout -b demo/choose-configuration

copy demo\ru\choose-configuration.mdx docs\ru\choose-configuration.mdx
copy demo\en\choose-configuration.mdx docs\en\choose-configuration.mdx

git add docs/ru/choose-configuration.mdx docs/en/choose-configuration.mdx
git commit -m "docs: choose-configuration page (RU + EN)"
git push -u origin demo/choose-configuration
```

Открыть новый PR по той же ссылке и повесить лейбл.
