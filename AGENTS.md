# Субагенты

## Podcast Translation Agent

Автономный субагент для перевода подкастов с YouTube.

### Установка

Скопируй файл субагента в директорию ~/.claude/agents/:

```bash
cp podcast-translator.md ~/.claude/agents/
```

Или установи из проекта:

```bash
# Файл уже создан в ~/.claude/agents/podcast-translator.md
```

### Как использовать

Из clawdbot или Claude Code:

**Простой запрос:**
```
Переведи этот подкаст: https://www.youtube.com/watch?v=gmkURB_HmQI
```

Claude автоматически определит и использует podcast-translator агента.

**Явный вызов:**
```
Используй podcast-translator агента для этого URL: https://www.youtube.com/watch?v=gmkURB_HmQI
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

### Конфигурация агента

**Имя**: `podcast-translator`
**Модель**: `sonnet`
**Инструменты**: `Bash, Read, Write, Edit`
**Расположение**: `~/.claude/agents/podcast-translator.md`

### Формат субагента

Субагенты используют YAML frontmatter:

```yaml
---
name: podcast-translator
description: Translates YouTube podcasts from English to Russian
tools: Bash, Read, Write, Edit
model: sonnet
---
```

За ним следует system prompt в Markdown формате.

### Документация

Подробнее о субагентах: https://code.claude.com/docs/en/sub-agents
