# Голоса для TTS

## Доступные голоса для русского языка

### Женские голоса

| Голос | ID | Описание |
|-------|----|----------|
| Dariya | `ru-RU-DariyaNeural` | Женский голос |
| Svetlana | `ru-RU-SvetlanaNeural` | Женский голос |

### Мужские голоса

| Голос | ID | Описание |
|-------|----|----------|
| Dmitry | `ru-RU-DmitryNeural` | Мужской голос (по умолчанию) |

## Как использовать

### В командной строке

**Голос по умолчанию (Dmitry)**:
```bash
python3 /home/clawd/work/podcast-translator/scripts/generate_tts.py \
  translations/podcast_ru.txt \
  audio/podcast_ru.mp3
```

**Женский голос (Svetlana)**:
```bash
python3 /home/clawd/work/podcast-translator/scripts/generate_tts.py \
  translations/podcast_ru.txt \
  audio/podcast_ru.mp3 \
  ru-RU-SvetlanaNeural
```

### С субагентом

При вызове podcast-translator агента он спросит какой голос использовать:

```
Переведи этот подкаст: https://www.youtube.com/watch?v=gmkURB_HmQI
Используй женский голос.
```

Или просто:
```
Переведи этот подкаст с женским голосом: [URL]
```

## Сравнение голосов

### Dmitry (мужской)
- Более низкий тембр
- Стандартный для технических подкастов
- Хорошая разборчивость

### Svetlana (женский)
- Более высокий тембр
- Более мягкое звучание
- Хорошая для образовательного контента

## Все доступные Edge TTS голоса

Для получения полного списка всех доступных голосов:

```bash
python3 -c "import edge_tts; print('\n'.join([v['Name'] for v in edge_tts.list_voices() if 'ru' in v['Locale']]))"
```

## Рекомендации

- **Технические подкасты**: Dmitry (мужской голос по умолчанию)
- **Образовательный контент**: Svetlana (женский голос)
- **Новостные выпуски**: Dmitry
- **Обучающие материалы**: Svetlana
