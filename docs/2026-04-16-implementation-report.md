# Hybrid Pipeline: Результаты реализации и план тестирования

**Дата:** 2026-04-16  
**Статус:** Реализация завершена, требуется ручное тестирование

---

## Что было сделано

### Проблема

Cron job `queue-processor` использовал `sessions_spawn` для порождения субагентов обработки видео. Этот подход регулярно обрывался по причинам:

1. Subagent announce зависит от WebSocket-доставки с таймаутом 120с на стороне gateway
2. ACP-процесс (claude-agent-acp) потреблял значительную память на Raspberry Pi (7.7 GB RAM)
3. Перезапуски gateway и ошибки моделей вызывали каскадные сбои субагентов
4. Таймаут `runTimeoutSeconds` существовал, но механизм announce сам по себе ненадёжен

### Решение: agentTurn + exec

Заменён `sessions_spawn` на `agentTurn` на встроенном агенте `work`. Агент выполняет весь пайплайн в одном ходе, вызывая Python-скрипты через `exec` и делая LLM-перевод в контексте.

### Изменённые файлы

#### 1. `process-queue.py` — добавлен флаг `--translate-only`

- Новый метод `translate_only(video_id)` в классе `QueueProcessor` (строка 291)
- Переводит одно видео через GoogleTranslator (из `deep_translator`)
- Сохраняет таймстемпы в формате `[MM:SS - MM:SS]`
- Вызывает `extract_tts_text.py` для генерации TTS-ready текста
- Возвращает dict с ключами `success`, `error`, `translation`, `tts_text`
- CLI: `python3 process-queue.py --translate-only <videoId>` — фолбэк при ошибке LLM-перевода

#### 2. `run_pipeline.py` — лаунчер с PID-lock (новый файл)

- PID-lock файл `/tmp/podcast-queue.lock` — предотвращает параллельный запуск
- Проверяет: если PID в lock-файле жив → выходит сразу (конкуренция)
- Если PID мёртв (устаревший lock) → удаляет lock и продолжает
- Вызывает `openclaw cron run <queue-processor-id>` с таймаутом 1800с
- Освобождает lock в `finally` + `atexit` + при SIGTERM
- CLI:
  - `python3 run_pipeline.py` — запуск пайплайна
  - `python3 run_pipeline.py --status` — статус (RUNNING/NOT RUNNING/STALE)
  - `python3 run_pipeline.py --force` — принудительный запуск

#### 3. Cron job `queue-processor` — новый payload

**ID:** `a79e58b0-f9bd-4911-86a7-44c01a1ae572`

Изменения:
- `timeoutSeconds`: 600 → **1800** (30 минут)
- `description`: "Queue Processor - agentTurn pipeline (no sessions_spawn)"
- Payload: полная инструкция пайплайна вместо `sessions_spawn` вызова
- Агент `work` получает пошаговые инструкции:
  1. `queue_manager.py next --json` — взять следующее видео
  2. `yt-dlp` — скачать MP3
  3. `transcribe_cached.py` — транскрипция whisper
  4. `prepare_transcript.py` — форматирование для перевода
  5. LLM-перевод EN→RU в контексте (фолбэк: `process-queue.py --translate-only`)
  6. `generate_tts.py` — генерация русской озвучки (edge-tts)
  7. `openclaw message send` — отчёт в Telegram
  8. `queue_manager.py complete` — пометить как готовое
  9. Повторить для следующего видео
- Отчёт в Telegram при каждой ошибке и после каждого видео
- Финальный саммари: "Queue: X done, Y failed, Z remaining"

#### 4. Cron job `youtube-collector` — каскад через `run_pipeline.py`

**ID:** `b15718ab-2323-465d-bb22-53c0b555b3dc`

Изменения:
- Payload изменён с `sessions_spawn` на `exec` вызов `run_pipeline.py`
- Тип payload: `systemEvent` (т.к. sessionTarget = "main")
- Лаунчер обеспечивает PID-lock контроль — если пайплайн уже запущен, тихо выходит

### Что НЕ изменялось

- `queue_manager.py` — без изменений
- `scripts/transcribe_cached.py` — без изменений
- `scripts/prepare_transcript.py` — без изменений
- `scripts/extract_tts_text.py` — без изменений
- `scripts/generate_tts.py` — без изменений
- Глобальный `agents.defaults.subagents.maxConcurrent` — без изменений

### Git-коммит

```
4727503 feat: hybrid pipeline — agentTurn + exec instead of sessions_spawn
```

---

## Шаги для тестирования

### Тест 1: Проверка статуса лаунчера

Цель: убедиться, что `run_pipeline.py` корректно определяет состояние блокировки.

```bash
# Пайплайн не запущен
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
# Ожидается: Pipeline is NOT running

# Имитация устаревшего lock (мёртвый PID)
echo "99999" > /tmp/podcast-queue.lock
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
# Ожидается: Pipeline lock is STALE (PID 99999 is dead)
rm -f /tmp/podcast-queue.lock

# Имитация активного lock (ваш собственный PID)
echo $$ > /tmp/podcast-queue.lock
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
# Ожидается: Pipeline is RUNNING (PID <ваш_PID>)
rm -f /tmp/podcast-queue.lock
```

### Тест 2: Защита от параллельного запуска

Цель: убедиться, что два одновременных вызова не приведут к двойной обработке.

Терминал 1:
```bash
echo $$ > /tmp/podcast-queue.lock
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py
# Ожидается: STATUS: Pipeline already running (PID ...) и выход с кодом 0
```

Терминал 2 (одновременно):
```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py
# Ожидается: STATUS: Pipeline already running (PID ...) и выход с кодом 0
```

Очистка: `rm -f /tmp/podcast-queue.lock`

### Тест 3: Флаг --translate-only

Цель: убедиться, что GoogleTranslator-фолбэк работает.

```bash
# Без подходящего файла — фолбэк на последний ready-файл
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/process-queue.py --translate-only test123
# Ожидается: STATUS: Translating ... via GoogleTranslator
#            SUCCESS: Translation saved: ...

# Без аргумента — ошибка
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/process-queue.py --translate-only
# Ожидается: Error: --translate-only requires a video ID
```

### Тест 4: Dry-run с пустой очередью

Цель: проверить, что `work`-агент корректно обрабатывает пустую очередь и отправляет отчёт в Telegram.

```bash
# Убедимся, что очередь пуста
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/queue_manager.py status
# Ожидается: Pending: 0, Processing: 0

# Запуск cron job вручную
openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572
```

**Проверить в Telegram:**
- Сообщение от `work`-агента: "Queue: 0 done, 0 failed, 0 remaining"

### Тест 5: Полный пайплайн с реальным видео (основной тест)

Цель: проверить весь цикл от скачивания до TTS с Telegram-отчётами.

**Шаг 5.1: Добавить тестовое видео**

Выберите короткое видео (до 5 минут для быстрого теста):

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 queue_manager.py add VIDEO_ID "Название видео" "Канал"
```

Пример с коротким видео:
```bash
python3 queue_manager.py add dQw4w9WgXcQ "Rick Astley - Never Gonna Give You Up" "RickAstleyYT"
```

**Шаг 5.2: Проверить, что видео в очереди**

```bash
python3 queue_manager.py status
# Ожидается: Pending: 1
```

**Шаг 5.3: Запустить пайплайн**

```bash
openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572
```

Или через лаунчер:
```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py
```

**Шаг 5.4: Следить за прогрессом**

В Telegram должны прийти сообщения:
1. "Done: Rick Astley - Never Gonna Give You Up" (при успехе)
2. ИЛИ "Failed: Rick Astley - Never Gonna Give You Up - <ошибка>" (при ошибке)
3. "Queue: 1 done, 0 failed, 0 remaining" (финальный саммари)

**Шаг 5.5: Проверить выходные файлы**

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator

# Скачанный MP3
ls -la input/dQw4w9WgXcQ.mp3

# Транскрипт
ls -la transcripts/dQw4w9WgXcQ.txt

# Перевод
ls -la translations/dQw4w9WgXcQ_ready.txt
ls -la translations/dQw4w9WgXcQ_ru_tts.txt

# Русская озвучка
ls -la audio/dQw4w9WgXcQ.ru.mp3
```

**Шаг 5.6: Проверить состояние очереди**

```bash
python3 queue_manager.py status
# Ожидается: Pending: 0, Completed: N (где N увеличилось на 1)
```

**Шаг 5.7: Проверить лаунчер после завершения**

```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
# Ожидается: Pipeline is NOT running (lock должен быть снят)
```

### Тест 6: Обработка ошибки при скачивании

Цель: убедиться, что пайплайн корректно обрабатывает сбой и продолжает со следующим видео.

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator

# Добавить несуществующее видео
python3 queue_manager.py add INVALID_VIDEO_ID "Test Invalid Video" "Test"

# Добавить нормальное видео после него
python3 queue_manager.py add dQw4w9WgXcQ "Rick Astley - Never Gonna Give You Up" "RickAstleyYT"

# Запустить
openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572
```

**Проверить в Telegram:**
1. "Failed: Test Invalid Video - Download failed" (или аналогичная ошибка)
2. "Done: Rick Astley - Never Gonna Give You Up" (второе видео обработано)
3. "Queue: 1 done, 1 failed, 0 remaining" (финальный саммари)

**Проверить очередь:**
```bash
python3 queue_manager.py status
# Ожидается: Pending: 0, Failed: N+1
```

### Тест 7: Каскад youtube-collector → run_pipeline.py

Цель: проверить, что youtube-collector правильно запускает пайплайн через лаунчер.

```bash
# Запустить youtube-collector вручную
openclaw cron run b15718ab-2323-465d-bb22-53c0b555b3dc
```

**Проверить:**
1. `channel_monitor.py` отработал — найдены/не найдены видео
2. Если видео добавлены — `run_pipeline.py` запущен, lock-файл создан
3. Если видео не найдены — пайплайн не запускается
4. В Telegram — отчёт youtube-collector'а

### Тест 8: Таймаут лаунчера (опционально)

Цель: убедиться, что лаунчер корректно завершает процесс после 30 минут.

Для этого теста нужно видео длиной более 25 минут (чтобы транскрипция заняла много времени). Лаунчер имеет таймаут 1800с, а `work`-агент должен остановиться после ~25 минут и отправить частичный саммари.

```bash
# Добавить длинное видео (опционально)
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 queue_manager.py add LONG_VIDEO_ID "Long Podcast Episode" "Channel"

# Запустить и ждать
openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572
```

---

## Критерии успеха

Тест считается пройденным, если:

1. **Пайплайн завершается** без ошибок gateway/subagent announce
2. **Telegram-отчёты** приходят после каждого видео
3. **Выходные файлы** создаются корректно (MP3, .txt, _ru_tts.txt, .ru.mp3)
4. **Очередь** обновляется (pending → completed или failed)
5. **Lock-файл** снимается после завершения
6. **При ошибке** пайплайн продолжает следующее видео (не падает целиком)
7. **Параллельный запуск** блокируется лаунчером

## Откат (если что-то пойдёт не так)

Cron job можно вернуть к предыдущей конфигурации:

```bash
openclaw cron edit a79e58b0-f9bd-4911-86a7-44c01a1ae572 \
  --description "Queue Processor - Sequential processing with sessions_spawn" \
  --timeout-seconds 600 \
  --message '<старый_payload>'
```

Старый payload сохранён в git-истории коммита перед `4727503`.

## Мониторинг в продакшене

После успешного тестирования:

1. Следите за логами gateway: `tail -f /tmp/openclaw/openclaw-*.log | grep queue-processor`
2. Проверяйте состояние очереди: `python3 queue_manager.py status`
3. Следите за Telegram — отчёты должны приходить каждые 2 часа (если есть видео)
4. При накоплении ошибок: `python3 queue_manager.py clear-old` для очистки старых записей