# CLI Flex и рабочий план `tw`

Дата среза: 2026-06-07.

Этот файл объясняет, как пользоваться `tw` без постоянной возни с `draft_id`, что делают основные флаги, где лежит память, и что происходит под капотом.

Главное правило: система делает только черновики. Она не публикует в X/Twitter, не вызывает записывающие X API и не имеет команды публикации.

## Самый короткий режим

Обычный ежедневный режим:

```powershell
tw draft "текст мысли"
```

По умолчанию это означает:

- короткий пост;
- вызов Codex через командную строку;
- модель `gpt-5.5`;
- усилие рассуждения `xhigh`;
- скорость `fast`;
- проверка под рекомендации X включена;
- личный стиль `tg_crypto_clean` включается сам, если профиль уже построен;
- новый черновик становится текущим активным черновиком.

Если Codex CLI не найден или вернул неразбираемый ответ, команда падает с ошибкой. Тихого перехода в ручной режим нет. Запасной локальный режим включается только явно:

```powershell
tw draft --no-llm "текст мысли"
```

## Активный черновик

Чтобы не таскать `draft_id`, система хранит один текущий черновик:

```text
~/twitter-system/state/current_draft.txt
```

Там лежит только id активного черновика. Новый `tw draft ...` автоматически делает созданный черновик активным.

Команды без `draft_id` работают по активному черновику:

```powershell
tw show
tw path
tw edit "сделай короче и менее уверенно"
tw review
tw algo
tw ready
tw reject
```

Список черновиков:

```powershell
tw drafts
tw drafts --limit 5
```

В списке `*` показывает активный черновик. Номер слева можно использовать для переключения:

```powershell
tw use 2
tw use latest
tw use 20260607-...
```

Старый путь тоже работает:

```powershell
tw show latest
tw path latest
tw review latest
tw algo-review latest
```

Но для ручной работы теперь лучше думать так: "я работаю с одним текущим черновиком".

## Что создаёт `tw draft`

Черновики лежат в центральном хранилище:

```text
~/twitter-system/drafts/YYYY/MM/<draft_id>/
```

Базовые файлы:

```text
00_raw_input.md
01_context_used.md
02_brief.md
03_variants.md
04_critique.md
05_selected.md
06_final_candidate.md
prompt_to_codex.md
meta.yaml
```

Файлы проверки под X:

```text
07_algorithm_review.md
08_media_plan.md
09_distribution_plan.md
```

Файлы личного стиля, если `tg_crypto_clean` включен:

```text
10_identity_style_review.md
11_examples_used.md
12_risk_flags.md
```

Файлы контекста и вызова Codex:

```text
13_context_bundle.md
13_context_bundle.json
14_llm_request.md
15_llm_raw_output.md
16_llm_parse_report.md
AGENTS.override.md
.codex_home/AGENTS.md
.codex_home/config.toml
```

`15_llm_raw_output.md` появляется, когда модель реально вызывалась.

## Что происходит под капотом

Когда ты пишешь:

```powershell
tw draft "мысль"
```

система делает так:

1. Берёт текст мысли.
2. Определяет текущий проект по папке запуска.
3. Обновляет краткий контекст проекта в центральном хранилище.
4. Убирает секретоподобные строки из входного текста.
5. Ищет похожую память: идеи, черновики, посты, источники, Telegram.
6. Создаёт папку черновика.
7. Пишет базовые варианты и служебные файлы.
8. Если есть `tg_crypto_clean`, добавляет слой личного стиля.
9. Собирает `13_context_bundle.md/json`.
10. Пишет `14_llm_request.md`.
11. Создаёт `AGENTS.override.md` и отдельный `.codex_home`.
12. Запускает Codex из папки черновика, а не из папки проекта.
13. Парсит ответ как JSON.
14. Обновляет `03_variants.md`, `04_critique.md`, `05_selected.md`, `06_final_candidate.md`.
15. Записывает отчёт `16_llm_parse_report.md`.
16. Добавляет алгоритмическую проверку `07-09`.
17. Делает этот черновик активным.

Почему Codex запускается из папки черновика: чтобы он не подхватил случайный `AGENTS.md` из проекта с кодом. Кодовый `AGENTS.md` можно кратко использовать как контекст, но он не должен становиться активной инструкцией для написания поста.

## Флаги `tw draft`

Формат:

```powershell
tw draft [флаги] "текст мысли"
```

Тип черновика:

```text
--short
--thread
--article-note
--build-log
--question
```

Если ничего не указать, используется `--short`.

Контекст:

```text
--url <ссылка>
```

Добавляет ссылку как источник.

```text
--context-only
```

Собирает папку, контекст и запрос для Codex, но не вызывает модель.

```text
--print-prompt-path
```

Печатает путь к `14_llm_request.md`. Обычно используется вместе с `--context-only`.

Модель:

```text
--llm auto|codex
```

`auto` сейчас означает Codex CLI. OpenAI API в обычном CLI не используется.

```text
--model <имя>
--reasoning-effort low|medium|high|xhigh
--speed <значение>
```

Переопределяют модель, усилие и скорость на один запуск.

```text
--no-llm
```

Не вызывает Codex. Делает локальный запасной черновик.

```text
--require-llm
```

Явно требует успешного вызова модели. Сейчас обычный режим и так строгий, но флаг оставлен как явное намерение.

Алгоритмическая проверка:

```text
--algo-aware
--no-algo-aware
```

`--algo-aware` включен по умолчанию. `--no-algo-aware` отключает файлы `07-09` на один запуск.

Личный стиль:

```text
--identity-style <profile>
--identity-style none
--identity-strength <число>
```

Если `tg_crypto_clean` построен, он включается сам с силой `0.35`. `--identity-style none` отключает личный стиль на один запуск.

## Правка черновика

Главная команда:

```powershell
tw edit "инструкция"
```

Примеры:

```powershell
tw edit "сделай короче"
tw edit "оставь мысль, но убери уверенность и финансовый тон"
tw edit "сделай более похоже на build log"
```

Что происходит:

1. Берётся активный черновик.
2. В папку черновика пишется `17_edit_request.md`.
3. Codex вызывается из этой же папки.
4. Сырой ответ сохраняется в `18_edit_raw_output.md`.
5. Ответ парсится как JSON с полем `final_candidate`.
6. Новый текст пишется в `06_final_candidate.md`.
7. Ревизия сохраняется в `revisions/`.
8. Отчёт пишется в `19_edit_parse_report.md`.

Можно явно указать черновик:

```powershell
tw edit --draft-id latest "сделай короче"
```

Но обычный режим без id теперь предпочтительный.

## Просмотр и статус

Показать финальный текст активного черновика:

```powershell
tw show
```

Показать путь к папке:

```powershell
tw path
```

Открыть папку:

```powershell
tw open
```

Пометить готовым:

```powershell
tw ready
```

Отклонить:

```powershell
tw reject
```

Локально отметить, что человек сам уже опубликовал пост:

```powershell
tw posted --url "https://x.com/..."
```

Это не публикация. Это только запись факта в локальную память.

Старые команды тоже работают:

```powershell
tw mark-ready latest
tw mark-posted latest --url "https://x.com/..."
```

## Проверки черновика

Общая проверка:

```powershell
tw review
```

Все X-fit слои сразу:

```powershell
tw algo
```

По отдельности:

```powershell
tw algo-review
tw media-plan
tw distribution-plan
```

Личный стиль:

```powershell
tw style-review
tw style-review --profile tg_crypto_clean --identity-strength 0.35
```

Все эти команды берут активный черновик, если id не указан.

## Поиск в памяти

Обычный поиск:

```powershell
tw search "execution assumptions"
```

Флаги:

```text
--limit <число>
```

Обычный поиск сейчас простой: он ищет слова запроса в локальной SQLite-памяти по идеям, черновикам, постам, источникам и Telegram-сообщениям. Это не векторный поиск и не модельная семантика.

Умный поиск через Codex:

```powershell
tw search --smart "execution assumptions"
```

Что происходит:

1. Система сначала делает обычный поиск и собирает кандидатов.
2. Учитывает текущий проект, чтобы близкие проектные куски были выше.
3. Пишет кандидатов в:

```text
~/twitter-system/searches/<search_id>/01_candidates.md
```

4. Пишет запрос к Codex:

```text
02_codex_request.md
```

5. Запускает Codex CLI в отдельной search-папке.
6. Сохраняет ответ:

```text
03_codex_raw_output.md
04_search_report.md
```

7. Печатает объяснение в терминал.

`tw search --smart` не создаёт посты и ничего не публикует. Он только помогает найти нужные черновики, идеи и источники.

## Идеи и память

Сохранить мысль без создания поста:

```powershell
tw idea "мысль"
```

Где хранится:

```text
~/twitter-system/inbox/ideas.md
~/twitter-system/db/content.sqlite
```

Потом эта идея попадает в поиск и в подбор похожей памяти для новых черновиков.

## `init` и `ensure`

```powershell
tw init
tw ensure
```

Обе команды создают центральное хранилище, если его ещё нет. Они не создают базу в текущем проекте.

По умолчанию:

```text
~/twitter-system/
```

База:

```text
~/twitter-system/db/content.sqlite
```

Можно переопределить корень:

```powershell
$env:TWITTER_SYSTEM_ROOT = ".tmp-twitter-system\smoke"
tw ensure
```

`ensure` можно запускать сколько угодно раз. Это безопасная идемпотентная команда.

## Личный стиль `tg_crypto_clean`

Импорт:

```powershell
tw tg-import "C:\Users\v-353\Downloads\tg_identity_pack.zip" --profile tg_crypto_clean
tw style-build tg_crypto_clean --auto
```

Автоматический выбор:

- `auto_gold` используется как безопасные примеры стиля;
- `auto_neutral` слабее, запасной слой;
- `auto_reject` не используется для стиля;
- `auto_source_only` может быть темой или источником, но не голосом;
- `forwarded_other` не становится стилевым примером.

Если профиль построен, обычный `tw draft "..."` подключает его сам. Отключить:

```powershell
tw draft --identity-style none "мысль"
```

## Style/content gold

Если есть готовый пакет с сильными примерами стиля и структуры:

```powershell
tw style-gold-import "C:\Users\v-353\Downloads\style_content_gold.zip"
```

Команда кладёт в профиль:

```text
~/twitter-system/profile/style_gold.md
~/twitter-system/profile/content_gold.md
~/twitter-system/profile/style_content_gold_report.md
```

Смысл:

- `style_gold.md` — ритм, прямота, живая формулировка;
- `content_gold.md` — структура мысли, треда, разбора, аргумента;
- эти файлы используются в `tw codex` как reference слой;
- копировать старый crypto/market контент буквально нельзя;
- переносить надо механику мысли, а не шиллинг, прогнозы или финансовые советы.

## Нативная папка Codex для финальной доводки

Когда уже есть разбор статьи, почти готовый тред или сильный черновик, лучше использовать не `tw draft`, а отдельную Codex-папку:

```powershell
tw codex --prepare
tw codex --prepare --thread
tw codex --prepare --file "C:\path\article_notes.md" --thread
tw codex --run
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

Это решает конфликт двух `AGENTS.md`:

```text
C:\N\hse\twitter-content-machine\AGENTS.md
  = инструкции для разработки кода

~/twitter-system/codex_sessions/<session_id>/AGENTS.md
  = инструкции для финальной доводки текста
```

`tw codex --prepare` только готовит папку и печатает путь.

`tw codex --run` запускает Codex из этой папки с изолированным `CODEX_HOME`.

Режим треда:

```powershell
tw codex --prepare --thread
```

Режим одиночного финального поста:

```powershell
tw codex --prepare --final-post
```

Готовый файл с заметками:

```powershell
tw codex --prepare --file "C:\path\article_notes.md" --thread
```

Конкретный черновик:

```powershell
tw codex latest --prepare
tw codex 20260607-... --prepare
```

Последняя Codex-session папка хранится тут:

```text
~/twitter-system/state/current_codex_session.txt
```

Codex внутри этой папки должен писать результат только в:

```text
output/
```

## X read-only

Синхронизация своих уже опубликованных постов:

```powershell
tw sync-posted
```

Анализ своих:

```powershell
tw analyze-own --sync
```

Чтение чужого аккаунта как источника:

```powershell
tw x-read @handle --limit 100
tw analyze-peer @handle --limit 100
```

Это только чтение. Чужие посты не становятся твоим стилем.

## Короткая ежедневная схема

Минимум:

```powershell
tw draft "мысль"
tw show
tw edit "сделай короче"
tw ready
```

Если надо найти старое:

```powershell
tw search --smart "примерная тема"
tw drafts
tw use 2
tw show
```

Если надо понять, что подал в модель:

```powershell
tw path
```

Потом открыть папку и смотреть:

```text
13_context_bundle.md
14_llm_request.md
15_llm_raw_output.md
16_llm_parse_report.md
```

## Что пока не сделано

Слабые места текущей версии:

- обычный поиск не векторный, а простой текстовый;
- `tw search --smart` ранжирует уже найденные кандидаты, но сам не делает полноценный семантический поиск по всей базе;
- ручное открытие папки всё ещё полезно для глубокого разбора;
- `tw edit` ожидает JSON от Codex, поэтому при кривом ответе команда упадёт и сохранит отчёт.

Следующее сильное улучшение: добавить векторную память или локальный semantic index, чтобы `tw search --smart` находил похожие идеи даже без совпадающих слов.
