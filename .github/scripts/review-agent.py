#!/usr/bin/env python3
"""
Docs Review Agent
=================
Читает diff PR + Vale JSON, загружает стайлгайд через MCP-сервер
(или fallback на локальные файлы), вызывает LLM и постит
inline-комментарии + сводное резюме в GitHub PR Review.

Переменные окружения (LLM):
    LLM_API_KEY   — API-ключ (обязательно)
    LLM_BASE_URL  — базовый URL для OpenAI-совместимого API
                    (если не задан — используется api.openai.com)
    LLM_MODEL     — имя модели (по умолчанию: gpt-4o-mini)

Использование (вызывается из GitHub Actions):
    python3 review-agent.py \
        --changed-files /tmp/changed_files.txt \
        --vale-output   /tmp/vale_output.json
"""

import argparse
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import requests
from openai import OpenAI

# ─── Константы ────────────────────────────────────────────────────────────────

DEFAULT_MODEL     = "gpt-4o-mini"   # используется если LLM_MODEL не задан
MAX_INLINE        = 20          # максимум inline-комментариев
MAX_FILES         = 10          # максимум файлов в одном запуске
MAX_DIFF_CHARS    = 60_000      # обрезаем diff до этого размера
MCP_TIMEOUT       = 10          # секунд на запрос к MCP
STYLE_GUIDE_DIR   = Path(__file__).parent.parent.parent / "style_guide"

# ─── GitHub API ───────────────────────────────────────────────────────────────

def gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_pr_diff(repo: str, pr_number: str, token: str) -> str:
    """Возвращает unified diff PR как строку."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    resp = requests.get(
        url,
        headers={**gh_headers(token), "Accept": "application/vnd.github.v3.diff"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def post_review(
    repo: str,
    pr_number: str,
    token: str,
    comments: list[dict],
    summary: str,
) -> None:
    """
    Постит GitHub PR Review с типом COMMENT (никогда REQUEST_CHANGES).
    comments: [{"path": str, "line": int, "body": str}]
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "body": summary,
        "event": "COMMENT",          # только COMMENT, не REQUEST_CHANGES
        "comments": [
            {
                "path": c["path"],
                "line": c["line"],
                "side": "RIGHT",      # строка в новой версии файла
                "body": c["body"],
            }
            for c in comments
        ],
    }
    resp = requests.post(url, headers=gh_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] GitHub API {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        resp.raise_for_status()
    print(f"[OK] Review posted with {len(comments)} inline comment(s).")


def post_summary_only(repo: str, pr_number: str, token: str, summary: str) -> None:
    """Постит только сводное резюме без inline-комментариев."""
    post_review(repo, pr_number, token, [], summary)

# ─── MCP / Стайлгайд ──────────────────────────────────────────────────────────

def fetch_style_guide_mcp(mcp_url: str, mcp_key: str, section: str | None = None) -> str:
    """Запрашивает стайлгайд у MCP-сервера."""
    params = {"section": section} if section else {}
    resp = requests.get(
        f"{mcp_url}/tools/get_style_guide",
        headers={"Authorization": f"Bearer {mcp_key}"},
        params=params,
        timeout=MCP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # MCP возвращает {"content": "..."} или {"sections": {...}}
    if "content" in data:
        return data["content"]
    if "sections" in data:
        return "\n\n".join(data["sections"].values())
    return json.dumps(data)


def load_style_guide_local() -> str:
    """Fallback: читает локальные MD-файлы стайлгайда."""
    parts = []
    if not STYLE_GUIDE_DIR.exists():
        return "(стайлгайд недоступен)"
    for md in sorted(STYLE_GUIDE_DIR.glob("0*.md")):
        parts.append(md.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts) if parts else "(стайлгайд пуст)"


def get_style_guide(mcp_status: str, mcp_url: str, mcp_key: str) -> str:
    """Возвращает стайлгайд: MCP если доступен, иначе локальный fallback."""
    if mcp_status == "ok" and mcp_url and mcp_key:
        try:
            guide = fetch_style_guide_mcp(mcp_url, mcp_key)
            print("[OK] Style guide loaded from MCP server.")
            return guide
        except Exception as exc:
            print(f"[WARN] MCP fetch failed ({exc}), using local fallback.")
    else:
        print("[INFO] MCP unavailable, using local style guide.")
    return load_style_guide_local()

# ─── Vale ─────────────────────────────────────────────────────────────────────

def parse_vale_output(vale_json_path: str) -> dict[str, list[dict]]:
    """
    Парсит vale --output=JSON.
    Возвращает {filepath: [{"line": N, "message": str, "rule": str}]}
    """
    try:
        raw = Path(vale_json_path).read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

    result = {}
    for filepath, alerts in data.items():
        items = []
        for alert in alerts:
            items.append({
                "line":    alert.get("Line", 0),
                "message": alert.get("Message", ""),
                "rule":    alert.get("Check", ""),
                "severity": alert.get("Severity", "warning"),
            })
        if items:
            # Нормализуем путь (убираем ./ если есть)
            key = filepath.lstrip("./")
            result[key] = items
    return result


def format_vale_for_prompt(vale_results: dict[str, list[dict]]) -> str:
    """Форматирует Vale-предупреждения в читаемый текст для промпта."""
    if not vale_results:
        return "Vale не нашёл нарушений."
    lines = []
    for filepath, alerts in vale_results.items():
        lines.append(f"Файл: {filepath}")
        for a in alerts:
            lines.append(f"  Строка {a['line']}: [{a['rule']}] {a['message']}")
    return "\n".join(lines)

# ─── Diff helpers ─────────────────────────────────────────────────────────────

def extract_added_lines(diff: str, target_files: list[str]) -> dict[str, list[tuple[int, str]]]:
    """
    Извлекает добавленные строки из unified diff.
    Возвращает {filepath: [(line_number, text), ...]}
    """
    result: dict[str, list[tuple[int, str]]] = {}
    current_file = None
    new_line = 0

    for raw_line in diff.splitlines():
        # Заголовок файла
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            if current_file not in result:
                result[current_file] = []
            continue
        if raw_line.startswith("--- ") or raw_line.startswith("diff ") or raw_line.startswith("index "):
            continue

        # Hunk header: @@ -a,b +c,d @@
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            new_line = int(hunk.group(1)) - 1
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+"):
            new_line += 1
            if current_file in [f for f in target_files]:
                result[current_file].append((new_line, raw_line[1:]))
        elif not raw_line.startswith("-"):
            new_line += 1

    return result

# ─── Промпт ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Ты — строгий редактор технической документации.
Проверяй только изменённые строки (добавленные в PR).
Руководствуйся стайлгайдом и результатами Vale.

Правила:
- Комментируй только реальные нарушения стайлгайда. Молчание лучше шума.
- Максимум {max_inline} inline-комментариев. Выбирай самые важные.
- Не дублируй: если Vale уже точно указал нарушение, можешь добавить объяснение,
  но не повторяй одно и то же разными словами.
- Тон: нейтральный, конкретный. Не говори «хорошо» или «плохо».
  Говори что именно нарушено и как исправить.
- Не комментируй: код, JSX-теги, frontmatter (title/description),
  имена файлов, URL, технические термины.
- Язык комментариев: русский для docs/ru/, английский для docs/en/.

Ответь СТРОГО в формате JSON (без markdown-обёртки):
{{
  "comments": [
    {{"path": "docs/ru/example.mdx", "line": 42, "body": "Текст комментария"}}
  ],
  "summary": "Краткое резюме: что проверено, основные проблемы (2-4 предложения)."
}}
""".format(max_inline=MAX_INLINE)


def build_user_message(
    diff_excerpt: str,
    vale_text: str,
    style_guide: str,
    changed_files: list[str],
) -> str:
    # Обрезаем стайлгайд чтобы не выйти за лимит токенов
    MAX_GUIDE = 12_000
    guide_excerpt = style_guide[:MAX_GUIDE]
    if len(style_guide) > MAX_GUIDE:
        guide_excerpt += "\n\n[стайлгайд обрезан для экономии токенов]"

    return textwrap.dedent(f"""\
        ## Изменённые файлы
        {chr(10).join(changed_files)}

        ## Результаты Vale
        {vale_text}

        ## Diff (добавленные строки)
        ```diff
        {diff_excerpt}
        ```

        ## Стайлгайд
        {guide_excerpt}
    """)

# ─── OpenAI-совместимый LLM ───────────────────────────────────────────────────

def extract_json_from_response(raw: str) -> dict:
    """
    Извлекает JSON из ответа LLM.
    Обрабатывает три варианта:
    1. Чистый JSON-объект
    2. JSON внутри markdown-блока ```json ... ```
    3. JSON-объект, «утопленный» в тексте
    """
    raw = raw.strip()
    # Прямой парсинг
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Markdown-блок ```json ... ``` или ``` ... ```
    md_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass
    # Первый JSON-объект в тексте
    obj_match = re.search(r"\{[\s\S]+\}", raw)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Не удалось извлечь JSON из ответа LLM (первые 300 символов): {raw[:300]}")


def call_llm(
    system: str,
    user: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    max_retries: int = 3,
) -> dict:
    """
    Вызывает LLM через OpenAI-совместимый API, возвращает распарсенный JSON.
    При сбое выполняет до max_retries попыток с экспоненциальной задержкой.

    base_url — кастомный эндпоинт (например, внутренний прокси или локальный сервер).
               Если None, используется стандартный api.openai.com.
    model    — имя модели (например, «openai/gpt-oss-120b» или «gpt-4o-mini»).
    """
    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            # Пробуем сначала с json_object (OpenAI и совместимые),
            # при ошибке 400/422 — повторяем без response_format.
            call_kwargs: dict = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            try:
                response = client.chat.completions.create(
                    **call_kwargs,
                    response_format={"type": "json_object"},
                )
            except Exception as fmt_exc:
                # response_format не поддерживается провайдером
                print(f"[WARN] response_format не поддерживается, повтор без него: {fmt_exc}")
                response = client.chat.completions.create(**call_kwargs)

            raw = response.choices[0].message.content
            return extract_json_from_response(raw)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = 2 ** (attempt - 1)   # 1s, 2s, 4s
                print(f"[WARN] LLM попытка {attempt}/{max_retries} не удалась: {exc}. Повтор через {wait}с...")
                time.sleep(wait)
            else:
                print(f"[ERROR] LLM: все {max_retries} попытки исчерпаны.")

    raise last_exc  # type: ignore[misc]

# ─── Валидация комментариев ────────────────────────────────────────────────────

def validate_comments(
    comments: list[dict],
    diff_added: dict[str, list[tuple[int, str]]],
    changed_files: list[str],
) -> list[dict]:
    """
    Фильтрует комментарии:
    - только к реально изменённым (добавленным) строкам
    - только к файлам из changed_files
    - лимит MAX_INLINE
    """
    valid = []
    added_lines: dict[str, set[int]] = {
        fp: {ln for ln, _ in lines}
        for fp, lines in diff_added.items()
    }

    for c in comments:
        path = c.get("path", "")
        line = c.get("line")
        body = c.get("body", "").strip()

        if not path or not line or not body:
            continue
        # Нормализуем путь
        norm_path = path.lstrip("./")
        if norm_path not in changed_files:
            print(f"[SKIP] {norm_path}: не в списке изменённых файлов")
            continue
        # Комментарий должен быть на добавленной строке
        if norm_path not in added_lines or line not in added_lines[norm_path]:
            print(f"[SKIP] {norm_path}:{line}: строка не добавлена в этом PR")
            continue

        valid.append({"path": norm_path, "line": line, "body": body})
        if len(valid) >= MAX_INLINE:
            print(f"[INFO] Достигнут лимит {MAX_INLINE} комментариев.")
            break

    return valid

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-files", required=True,
                        help="Файл со списком изменённых путей (по одному на строку)")
    parser.add_argument("--vale-output", required=True,
                        help="JSON-вывод Vale")
    args = parser.parse_args()

    # Переменные окружения из GitHub Actions
    token      = os.environ["GITHUB_TOKEN"]
    repo       = os.environ["REPO"]
    pr_number  = os.environ.get("PR_NUMBER", "").strip()
    llm_key    = os.environ["LLM_API_KEY"]
    llm_base   = os.environ.get("LLM_BASE_URL") or None   # None → api.openai.com
    llm_model  = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    mcp_url    = os.environ.get("MCP_SERVER_URL", "")
    mcp_key    = os.environ.get("MCP_API_KEY", "")
    mcp_status = os.environ.get("MCP_STATUS", "unavailable")
    base_ref   = os.environ.get("BASE_REF", "main")

    # ── Ранний выход при workflow_dispatch без PR ─────────────────
    if not pr_number:
        print("[INFO] PR_NUMBER не задан (workflow_dispatch без PR). Выход без ошибки.")
        sys.exit(0)

    # ── Читаем список файлов ──────────────────────────────────────
    changed_files = [
        line.strip()
        for line in Path(args.changed_files).read_text().splitlines()
        if line.strip()
    ]
    if not changed_files:
        print("[INFO] Нет файлов для проверки. Выход.")
        sys.exit(0)

    # Ограничиваем количество файлов
    if len(changed_files) > MAX_FILES:
        print(f"[WARN] Файлов {len(changed_files)}, обрабатываем первые {MAX_FILES}.")
        changed_files = changed_files[:MAX_FILES]

    print(f"[INFO] Файлов для ревью: {len(changed_files)}")

    # ── Diff ─────────────────────────────────────────────────────
    print("[INFO] Загружаем diff PR...")
    diff = get_pr_diff(repo, pr_number, token)
    diff_excerpt = diff[:MAX_DIFF_CHARS]
    if len(diff) > MAX_DIFF_CHARS:
        print(f"[WARN] Diff обрезан до {MAX_DIFF_CHARS} символов.")

    diff_added = extract_added_lines(diff, changed_files)

    # ── Vale ─────────────────────────────────────────────────────
    vale_results = parse_vale_output(args.vale_output)
    vale_text    = format_vale_for_prompt(vale_results)
    print(f"[INFO] Vale: {sum(len(v) for v in vale_results.values())} предупреждений")

    # ── Стайлгайд ────────────────────────────────────────────────
    style_guide = get_style_guide(mcp_status, mcp_url, mcp_key)

    # ── LLM ──────────────────────────────────────────────────────
    endpoint_info = f"{llm_base or 'api.openai.com'} / {llm_model}"
    print(f"[INFO] Вызываем LLM: {endpoint_info}")
    user_msg = build_user_message(diff_excerpt, vale_text, style_guide, changed_files)
    try:
        result = call_llm(SYSTEM_PROMPT, user_msg, llm_key, model=llm_model, base_url=llm_base)
    except Exception as exc:
        print(f"[ERROR] LLM failed: {exc}", file=sys.stderr)
        vale_count = sum(len(v) for v in vale_results.values())
        post_summary_only(
            repo, pr_number, token,
            f"⚠️ **Docs Review**: LLM-анализ не удался (`{type(exc).__name__}: {exc}`).\n\n"
            f"**Vale** нашёл **{vale_count}** предупреждений:\n\n"
            + vale_text
        )
        sys.exit(0)  # Vale-результаты запощены — workflow не должен падать

    # ── Валидируем и постим ───────────────────────────────────────
    raw_comments = result.get("comments", [])
    summary      = result.get("summary", "Docs Review завершён.").strip()

    valid_comments = validate_comments(raw_comments, diff_added, changed_files)
    print(f"[INFO] Комментариев после валидации: {len(valid_comments)} (было {len(raw_comments)})")

    # Добавляем Vale-сводку к резюме если есть нарушения
    if vale_results:
        vale_count = sum(len(v) for v in vale_results.values())
        summary += f"\n\n---\n**Vale**: найдено {vale_count} предупреждени{'е' if vale_count == 1 else 'й'}."

    post_review(repo, pr_number, token, valid_comments, summary)


if __name__ == "__main__":
    main()
