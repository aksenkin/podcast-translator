# Субагенты и Skills

## Claude Code Agent

Автономный агент для перевода подкастов с YouTube.

### Расположение

- **Проект**: `agents/podcast-translator.md`
- **Системный**: `~/.claude/agents/podcast-translator.md`

### Конфигурация агента

```yaml
name: podcast-translator
description: Translates YouTube podcasts from English to Russian. Downloads audio, transcribes, translates, and generates TTS.
tools: Bash, Read, Write, Edit
model: sonnet
```

### Как использовать

**Простой запрос:**
```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

**Явный вызов:**
```
Используй podcast-translator агента для этого URL
```

**С выбором голоса:**
```
Переведи этот подкаст с женским голосом
```

### Что делает агент

1. 📹 Скачивает аудио с YouTube
2. 🎤 Транскрибирует в английский текст
3. 🌍 Подготавливает для перевода
4. 🇷🇺 Переводит на русский
5. 🔊 Генерирует русскую озвучку

### Результат

Агент вернёт:
- Пути ко всем созданным файлам
- Длительность аудио
- Количество слов в переводе
- Размеры файлов

### Доступные голоса

- `ru-RU-DmitryNeural` - Мужской голос (по умолчанию)
- `ru-RU-SvetlanaNeural` - Женский голос
- `ru-RU-DariyaNeural` - Женский голос

## OpenClaw Skill 🎙️

Автоматический skill для OpenClaw с полным pipeline.

### Расположение

- **Проект**: `skills/podcast-translator/SKILL.md`

### Конфигурация skill

```yaml
name: podcast-translator
description: "Translate YouTube podcasts from English to Russian with TTS generation..."
emoji: "🎙️"
requires: { "bins": ["yt-dlp", "python3"] }
```

### Как использовать

Просто отправь YouTube URL:

```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

**С выбором голоса:**
```
Переведи этот подкаст с женским голосом: [URL]
```

### Особенности

- Автоматически распознаёт YouTube URLs
- Спавнит субагент для выполнения pipeline
- Возвращает результаты по готовности
- Работает асинхронно (не блокирует conversation)

## Формат агента

Агенты используют YAML frontmatter:

```yaml
---
name: podcast-translator
description: Translates YouTube podcasts from English to Russian
tools: Bash, Read, Write, Edit
model: sonnet
---
```

За ним следует system prompt в Markdown формате.

## Документация

- [Подробнее о субагентах](https://code.claude.com/docs/en/sub-agents)
- [OpenClaw Skills документация](https://openclaw.dev/docs/skills)
