# Backlog: обучение `tg_crypto_clean` на будущих постах

## Идея

Со временем `tg_crypto_clean` должен учиться не только на старом Telegram-экспорте и ручном gold-собрании, но и на новых постах, которые прошли через текущую content-machine:

- финальные кандидаты, которые человек реально одобрил;
- посты, вручную опубликованные человеком и потом отмеченные через `tw posted`;
- сильные `ready`-черновики, если пользователь явно разрешил брать их как стиль;
- переработанные треды и article notes после финального Codex-прогона.

Цель: стиль должен постепенно сдвигаться от старой crypto-era базы к живому текущему письму про markets, systems, ML infra, build logs и исследования.

## Почему это сильная идея

Старый Telegram хорошо даёт ритм, прямоту, способ думать и личные языковые паттерны. Но он может тащить старые риски: crypto shilling, price-call тон, аирдропы, промо и слишком каналовый стиль.

Новые одобренные посты лучше отражают текущую задачу:

- как пользователь реально пишет сейчас;
- какие темы уже становятся стабильным профилем;
- какие форматы прошли human review;
- какие формулировки не выглядят как GPT/LinkedIn;
- какие идеи не надо повторять.

## Что нельзя импортировать как стиль

Нельзя автоматически добавлять в `tg_crypto_clean`:

- rejected drafts;
- peer posts из `tw x-read`;
- чужие источники и статьи;
- Telegram `forwarded_other`;
- черновики, где Codex сильно исказил мысль;
- финансовые советы, price calls, shill, аирдроп-инструкции;
- декоративные или generic-посты, которые прошли случайно.

Чужой материал может быть source/topic memory, но не user style.

## Будущие команды

Реализованный минимальный набор:

```powershell
tw style-learn
tw style-refresh
tw style-stats
```

`ready` и `posted` намеренно считаются одним классом: approved own writing.
Отдельного `--draft latest` нет: если текст надо использовать как стиль,
сначала он должен быть явно помечен как `ready` или `posted`.

Возможные метки:

```text
own_posted
processed_post_gold
processed_post_neutral
processed_post_reject
source_only
```

## Где хранить

Предлагаемые артефакты:

```text
~/twitter-system/identity_styles/tg_crypto_clean/post_gold_examples.md
~/twitter-system/identity_styles/tg_crypto_clean/processed_posts_report.md
~/twitter-system/identity_styles/tg_crypto_clean/post_gold_examples.md
```

В базе можно хранить отдельный источник `processed_posts`, чтобы не смешивать Telegram, X sync, peer posts и свои финальные тексты.

## Главный риск

Появится feedback loop: система начнёт учиться на собственных же сгенерированных фразах и постепенно станет уже, суше и более шаблонной.

Защита:

- брать только human-approved или manually posted тексты;
- хранить причину включения примера;
- ограничивать долю processed posts в контексте;
- сохранять Telegram/style_gold как внешний якорь ритма;
- регулярно флагать повторяющиеся фразы и идеи.

## MVP будущего слоя

Реализованный MVP:

1. `tw ready` и `tw posted --url ...` помечают собственные одобренные тексты.
2. `tw style-learn` выбирает только безопасные собственные тексты из `ready`, `posted` и локальной таблицы `posts`.
3. Команда пишет `processed_posts_report.md` и `post_gold_examples.md`.
4. Новые примеры хранятся отдельно от Telegram в `processed_style_examples`.
5. В `11_examples_used.md` могут появляться processed post examples как отдельный источник, не смешанный с Telegram.
