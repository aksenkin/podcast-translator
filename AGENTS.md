# Субагенты

## Podcast Translation Agent

Автономный субагент для перевода подкастов с YouTube.

### Как использовать

Из clawdbot или другого Claude Code сессии:

```
Запусти субагента для перевода подкаста.

Задача: Прочитай /home/clawd/work/podcast-translator/agents/podcast-translator.md и выполни задачу для URL: https://www.youtube.com/watch?v=VIDEO_ID

Субагент должен выполнить весь pipeline автономно и вернуться с результатами.
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

### Пример вызова

```
Используй Agent tool чтобы запустить автономный субагента:

Prompt: "Прочитай /home/clawd/work/podcast-translator/agents/podcast-translator.md и переведи этот подкаст: https://www.youtube.com/watch?v=gmkURB_HmQI"
Subagent type: general-purpose

Дождись завершения и покажи мне результаты.
```
