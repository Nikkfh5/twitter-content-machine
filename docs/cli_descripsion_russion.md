# CLI Description Russian

Русский справочник по `tw`. Это не полный dump всех флагов, а рабочая схема:
что писать в терминал каждый день и что происходит под капотом.

Главная идея: минимум текста в командной строке.

```powershell
tw draft "текст мысли"
```

По умолчанию это уже включает:

- Codex CLI;
- модель `gpt-5.5`;
- reasoning `xhigh`;
- speed `fast`;
- ожидание Codex до 600 секунд;
- progress-сообщения в stderr, пока Codex работает;
- короткий формат;
- английский итоговый пост, даже если мысль введена на русском;
- algorithm-aware review;
- личный стиль, если стиль уже построен;
- запись всех артефактов в центральный `~/twitter-system`.

OpenAI API не используется. Автопостинга нет.

---

## 1. Самые частые команды

### Создать черновик

```powershell
tw draft "сегодня понял что execution assumptions в бэктесте важнее модели"
```

Это основной режим. Обычно больше ничего писать не нужно.
Текст мысли можно писать по-русски или смешанно, но `03_variants.md`,
`05_selected.md` и `06_final_candidate.md` должны получаться на английском.

Что создаётся:

```text
00_raw_input.md
01_context_used.md
02_brief.md
03_variants.md
04_critique.md
05_selected.md
06_final_candidate.md
07_algorithm_review.md
08_media_plan.md
09_distribution_plan.md
10_identity_style_review.md
11_examples_used.md
12_risk_flags.md
13_context_bundle.md
13_context_bundle.json
14_llm_request.md
15_llm_raw_output.md
16_llm_parse_report.md
AGENTS.md
AGENTS.override.md
.codex_home/AGENTS.md
```

Codex запускается из папки черновика, поэтому активные инструкции для генерации
берутся из draft-local `AGENTS.md`, а не из `AGENTS.md` кодового проекта.
Изолированный `CODEX_HOME` включается только если в `.codex_home` уже есть auth;
иначе используется обычная авторизация Codex, но рабочая папка всё равно остаётся
папкой черновика.

Если Codex CLI не найден или сломался, обычный `tw draft "..."` падает с ошибкой.
Локальный шаблонный fallback включается только явно через `--no-llm`.

Если проект большой, `tw draft` может несколько минут ждать Codex. Это нормально:
он печатает строки вида `tw: codex started`, `tw: codex still working`,
`tw: codex finished`, чтобы терминал не выглядел зависшим.

### Посмотреть текущий черновик

```powershell
tw show
```

Показывает финальный кандидат из активного черновика.

### Отредактировать текущий черновик через Codex

```powershell
tw edit "сделай короче и менее уверенно"
tw edit "убери GPT-формулировки"
tw edit "сделай более похожим на build note"
```

`tw edit` лучше старого `tw refine --pass ...`, потому что можно писать нормальную инструкцию словами.

### Проверить черновик

```powershell
tw review
tw algo
```

`tw review` делает общую проверку текста.

`tw algo` пересобирает сразу три файла:

```text
07_algorithm_review.md
08_media_plan.md
09_distribution_plan.md
```

Отдельные команды `tw algo-review`, `tw media-plan`, `tw distribution-plan` оставлены как старые/точечные, но обычно не нужны.

### Пометить готовым

```powershell
tw ready
```

Это локальная метка. Она не публикует пост.

`ready` значит: текст достаточно хороший, чтобы считать его твоим одобренным примером.

### Пометить опубликованным вручную

```powershell
tw posted --url "https://x.com/..."
```

Это тоже только локальная метка. Команда не пишет в X.

`posted` значит: ты сам вручную опубликовал пост, а CLI сохранил факт и текст в память.

### Отклонить

```powershell
tw reject
```

Отклонённые черновики не должны попадать в личный стиль.

---

## 2. Активный черновик

После `tw draft "..."` новый черновик становится активным.

Поэтому обычно не надо писать `draft_id`.

```powershell
tw show
tw edit "сделай проще"
tw review
tw algo
tw ready
tw posted --url "https://x.com/..."
```

Где хранится указатель:

```text
~/twitter-system/state/current_draft.txt
```

Это только указатель на текущий черновик, не база знаний.

### Список черновиков

```powershell
tw drafts
tw drafts --limit 5
```

`*` показывает активный черновик.

### Переключиться на другой черновик

```powershell
tw use 2
tw use latest
```

### Путь к активному черновику

```powershell
tw path
```

`tw open --print-path` больше не нужен. Используй `tw path`.

---

## 3. Форматы черновика

Обычно формат не указываем:

```powershell
tw draft "мысль"
```

Это короткий пост.

Если нужен другой формат:

```powershell
tw draft --thread "разбор статьи про validation leaks"
tw draft --build-log "сегодня сломался cache key"
tw draft --question "как лучше моделировать fills без full LOB?"
tw draft --article-note --url "https://example.com/article"
```

`--short` писать не нужно, потому что short уже default.

---

## 4. Личный стиль

В нормальном режиме есть один общий стиль. В командах его имя писать не надо.

Первичная настройка:

```powershell
tw tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip"
tw style-build --auto
tw style-gold-import "C:\Users\v-353\Downloads\style_content_gold.zip"
```

Обновить стиль:

```powershell
tw style-refresh
tw style-stats
```

### Учить стиль на своих новых постах

```powershell
tw style-learn
```

Команда берёт только твои одобренные тексты:

- `ready`;
- `posted`;
- собственные строки из локальной таблицы `posts`.

`ready` и `posted` для этого слоя считаются одним классом: approved own writing.

Команда не берёт:

- rejected drafts;
- обычные draft-only черновики;
- peer posts;
- X-read внешние источники;
- статьи;
- Telegram `forwarded_other`;
- чужие тексты.

Что пишет:

```text
~/twitter-system/identity_styles/tg_crypto_clean/processed_posts_report.md
~/twitter-system/identity_styles/tg_crypto_clean/post_gold_examples.md
~/twitter-system/identity_styles/tg_crypto_clean/style_stats.md
```

Внутреннее имя профиля всё ещё `tg_crypto_clean`, но руками его обычно не пишем.

---

## 5. Поиск

Обычный поиск:

```powershell
tw search "execution assumptions"
```

Это простой локальный поиск по памяти.

Умный поиск:

```powershell
tw search --smart "execution assumptions"
```

`--smart` берёт найденные локальные кандидаты и просит Codex ранжировать/объяснить их.
Он ничего не публикует и не создаёт посты.

Логи поиска:

```text
~/twitter-system/searches/
```

---

## 6. Codex-папка для ручной работы с готовыми материалами

Если уже есть файл с разбором статьи, заметками для треда или почти готовым постом:

```powershell
tw codex --prepare --file "C:\path\article_notes.md" --thread
tw codex --run
```

Или просто подготовить папку:

```powershell
tw codex --prepare
```

Что создаётся:

```text
~/twitter-system/codex_sessions/<session_id>/
  AGENTS.md
  TASK.md
  INPUT.md
  CONTEXT_BUNDLE.md
  OUTPUT_SCHEMA.md
  README.md
  output/
  .codex_home/AGENTS.md
  .codex_home/config.toml
```

Это отдельная content-only папка. Её `AGENTS.md` не равен repo `AGENTS.md`.

Используй этот режим, когда хочешь вручную работать с Codex в нормальной папке,
но с правильными инструкциями для постов, стиля и безопасности.

---

## 7. Где всё хранится

Центральный workspace:

```text
~/twitter-system/
```

Главные папки:

```text
drafts/           # черновики
identity_styles/  # личный стиль
profile/          # persona/style/gold files
projects/         # контекст проектов
searches/         # логи smart search
sources/          # статьи, X-read, Telegram
db/content.sqlite # база данных
state/            # current draft/session pointers
```

`tw` не должен писать в текущий проект по умолчанию. Он собирает контекст проекта
и сохраняет его централизованно в `~/twitter-system/projects/<project_id>/`.

---

## 8. X/Twitter

В MVP нет автопостинга.

Разрешены только read-only/import/status операции:

```powershell
tw sync-posted
tw analyze-own --sync
tw x-read @handle --limit 100
tw analyze-peer @handle --limit 100
```

`tw posted --url ...` не публикует. Это локальная отметка после того, как ты сам
руками опубликовал пост.

---

## 9. Отладочные и legacy-команды

Эти команды/флаги остаются в коде, но не должны быть ежедневным режимом.

### LLM debug

```powershell
tw draft --llm codex --model gpt-5.5 --reasoning-effort xhigh --speed fast "мысль"
tw draft --context-only --print-prompt-path "мысль"
tw draft --no-llm "мысль"
```

Зачем:

- проверить context bundle;
- проверить prompt;
- создать локальный fallback без Codex;
- debug, если Codex CLI сломался.

Обычно это не нужно.

### Отключить algorithm-aware

```powershell
tw draft --no-algo-aware "мысль"
```

Обычно не нужно, потому что algorithm-aware review включён по умолчанию.

### Старые команды-синонимы

```powershell
tw queue
tw mark-ready
tw mark-posted --url "https://x.com/..."
tw open --print-path
tw refine --pass human
tw algo-review
tw media-plan
tw distribution-plan
```

Предпочтительные замены:

```text
tw queue                         -> tw drafts
tw mark-ready                    -> tw ready
tw mark-posted --url ...         -> tw posted --url ...
tw open --print-path             -> tw path
tw refine --pass ...             -> tw edit "инструкция словами"
tw algo-review/media/distribution -> tw algo
```

---

## 10. Нормальный рабочий цикл

```powershell
tw draft "сырая мысль"
tw show
tw edit "сделай короче и живее"
tw review
tw algo
tw ready
```

Если потом вручную запостил:

```powershell
tw posted --url "https://x.com/..."
tw style-learn
```

Если не понравилось:

```powershell
tw reject
```

---

## 11. Что важно помнить

- `tw draft "..."` уже делает почти всё.
- `draft_id` обычно не нужен.
- `--short` обычно не нужен.
- `--algo-aware` обычно не нужен.
- `--llm`, `--model`, `--reasoning-effort`, `--speed` обычно не нужны.
- `ready` и `posted` оба считаются одобренным собственным письмом для `style-learn`.
- `style-learn` не учится на чужих постах и rejected/draft-only текстах.
- Автопостинга нет.
