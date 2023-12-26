import logging
import os
import sys
import time
from datetime import datetime
from datetime import timedelta

from telegram import Bot
from dotenv import load_dotenv
import requests

from exception import (
    NotAuthenticatedError,
    APIAnswerError,
    StatusError,
    UnknownAPIAnswerError,
)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: dict[str, str] = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

DATE_FORMAT = '%Y-%m-%dT%XZ'

STATUS_TEXT = (
    'Изменился статус проверки '
    'работы "{homework_name}". {verdict}'
)
DEFAULT_FROM_DATE = 0

# Тексты для ошибок.
ENV_VARIABLE_ERROR_TEXT = 'Ошибка переменной окружения: {env_value}'
TG_ID_ERROR_TEXT = 'Ошибка id чата телеграмм.'
SEND_MESSAGE_ERROR_TEXT = (
    'Ошибка при отправке сообщения: {message}. Детали: {details}'
)
API_TYPE_ERROR_TEXT = 'Некорректный тип ответа API: {response}'
VALUE_NOT_LIST_ERROR_TEXT = (
    'Значение ключа "{key_name}" '
    'не является списком. Тип ответа API: {response_type}'
)
MISSING_API_KEY_ERROR_TEXT = (
    'В ответе API отсутствует ожидаемый ключ: {key_name}'
)
FOR_GET_API_ANSWER_ERROR_TEXT = (
    '{text}'
    '\nПараметры запроса:'
    '\nEndpoint={endpoint};'
    'Headers={headers};'
    'Params={params}.\n'
    '\n{error}'
)
NETWORK_ERROR_TEXT = 'Ошибка сети при отправке GET-запроса!'
UNKNOWN_API_ERROR_TEXT = 'Неизвестная ошибка ответа API. Code: {status_code}'
NOT_CORRECT_STATUS_ERROR_TEXT = 'Неожиданный статус домашней работы: {status}'
KEYBOARD_INTERRUPT_TEXT = 'Принудительное завершение программы.'
CURRENT_DATE_TYPE_ERROR_TEXT = (
    'Неожиданный тип значения ключа '
    '"current_date" ответа API: {date_type}'
)

# Тексты для логов
CRITICAL_LOG_TEXT_FOR_ENV = (
    'Невозможно запустить программу, '
    'проверьте переменные окружения: {error}'
)
NOT_NEW_STATUS_LOG_TEXT = 'В ответе отсутствует новый статус: {homework}'
SENT_SUCCESSFULLY_LOG_TEXT = 'Сообщение: "{message}" - отправлено успешно.'
STANDARD_ERROR_LOG_TEXT = (
    'Произошла ошибка во время работы бота.'
    '\nПодробности:\n{error}'
)
LOG_TEXT_FOR_UNKNOWN_ERROR = (
    'Неизвестная ошибка в работе бота.'
    '\nПодробности:\n{error}'
)

FORMATTER = (
    '%(asctime)s - %(funcName)s - '
    '%(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format=FORMATTER,
    stream=sys.stdout
)


def check_tokens() -> None:
    """Проверяет переменные окружения."""
    tokens = (
        TELEGRAM_TOKEN,
        PRACTICUM_TOKEN,
        TELEGRAM_CHAT_ID
    )
    try:
        for token in tokens:
            if token == '' or token is None:
                raise ValueError(
                    ENV_VARIABLE_ERROR_TEXT.format(
                        env_value=token
                    )
                )
    except ValueError as error:
        logger.critical(
            CRITICAL_LOG_TEXT_FOR_ENV.format(
                error=error
            ),
            exc_info=True
        )
        raise


def send_message(bot: Bot, message: str) -> None:
    """Для отправки сообщения в телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SENT_SUCCESSFULLY_LOG_TEXT.format(message=message))
    except Exception as error:
        logger.error(
            SEND_MESSAGE_ERROR_TEXT.format(message=message, details=error),
            exc_info=True
        )


def check_response(response: dict) -> None:
    """Проверяет ответ API на соответствие с документацией."""
    if not (
        isinstance(response, dict)
        or issubclass(type(response), dict)
    ):
        raise TypeError(
            API_TYPE_ERROR_TEXT.format(response=type(response))
        )

    if 'homeworks' not in response:
        raise KeyError(
            MISSING_API_KEY_ERROR_TEXT.format(key_name="homeworks")
        )

    if not (
        isinstance(response.get('homeworks'), list)
        or issubclass(type(response.get('homeworks')), list)
    ):
        raise TypeError(
            VALUE_NOT_LIST_ERROR_TEXT.format(
                key_name='homeworks',
                response_type=type(response.get('homeworks'))
            )
        )


def get_api_answer(timestamp: int) -> dict:
    """
    Отправляет запрос к API.
    Возвращает ответ API.
    """
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        data_from_api = response.json()
    except Exception as error:
        raise ConnectionError(
            FOR_GET_API_ANSWER_ERROR_TEXT.format(
                text=NETWORK_ERROR_TEXT,
                endpoint=ENDPOINT,
                headers=HEADERS,
                params=timestamp,
                error=error
            )
        )
    else:
        if 'error' in data_from_api:
            raise APIAnswerError(
                f'Error: {data_from_api.get("error").get("error")}\n'
                f'Code: {data_from_api.get("cose")}'
            )

        if (
            'error' not in data_from_api
            and 'code' in data_from_api
        ):
            raise NotAuthenticatedError(
                f'Code: {data_from_api.get("code")}\n'
                f'Message: {data_from_api.get("message")}'
            )

        if response.status_code != 200:
            raise UnknownAPIAnswerError(
                FOR_GET_API_ANSWER_ERROR_TEXT.format(
                    text=UNKNOWN_API_ERROR_TEXT,
                    endpoint=ENDPOINT,
                    headers=HEADERS,
                    params=timestamp,
                    error=''
                )
            )

    check_response(data_from_api)

    return data_from_api


def parse_status(homework: dict) -> str:
    """Извлекает из информации конкретной домашней работы статус."""
    homework_keys = (
        'homework_name',
        'status',
    )

    for key in homework_keys:
        if key not in homework:
            raise KeyError(
                MISSING_API_KEY_ERROR_TEXT.format(
                    key_name=key
                )
            )

    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise StatusError(
            NOT_CORRECT_STATUS_ERROR_TEXT.format(status=homework.get("status"))
        )

    return STATUS_TEXT.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS.get(
            homework['status']
        )
    )


def get_from_date(api_answer: dict) -> int:
    """Обновляет отсечку времени по присланным данным из API."""
    try:
        if 'current_date' not in api_answer:
            raise KeyError(
                MISSING_API_KEY_ERROR_TEXT.format(
                    key_name='current_date'
                )
            )
        if not (
            isinstance(api_answer.get('current_date'), int)
            or issubclass(type(api_answer.get('current_date')), int)
        ):
            raise TypeError(
                CURRENT_DATE_TYPE_ERROR_TEXT.format(
                    date_type=type(api_answer.get('current_date'))
                )
            )
    except KeyError:
        logger.exception('Ошибка значения ключа current_date')
    except ValueError:
        logger.exception('Неожиданный тип значения ключа current_date')
    else:
        return int(api_answer.get('current_date'))
    finally:
        return DEFAULT_FROM_DATE


def send_error_message(bot: Bot, message: str, messages: list):
    """
    Отправляет в телеграм сообщение ошибки.
    Перед отправкой сверяется со списком уже отправленных сообщений:
    если аналогичное сообщение уже было отправлено,
    то отправка сообщения пропускается.
    """
    if message not in messages:
        send_message(bot, message)
        messages.append(message)


def logic_for_while_loop(timestamp: int, bot: Bot, messages: list):
    """Логика для цикла while функции main()."""
    try:
        api_answer = get_api_answer(timestamp)
        homework = api_answer.get('homeworks')

        if len(homework) > 0:
            send_message(bot, parse_status(homework[0]))
        else:
            logger.debug(NOT_NEW_STATUS_LOG_TEXT.format(
                homework=homework
            ))
        return get_from_date(api_answer)
    except APIAnswerError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except UnknownAPIAnswerError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except NotAuthenticatedError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except StatusError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except TypeError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except KeyError as error:
        message = STANDARD_ERROR_LOG_TEXT.format(error=error)
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except Exception as error:
        message = LOG_TEXT_FOR_UNKNOWN_ERROR.format(error=error)
        logger.exception(message)
        send_error_message(bot, message, messages)

    return DEFAULT_FROM_DATE


def clean_error_messages(clean_date: datetime, messages: list) -> datetime:
    """
    Удаляет отправленные сообщения об ошибках раз в сутки.
    Возвращает следующую дату обнуления списка сообщений
    если условие истинно. В противном случае возвращает ту же дату,
    что была получена в качестве аргумента.
    """
    if datetime.today() >= clean_date:
        messages.clear()
        return datetime.today() + timedelta(days=1)
    return clean_date


def main() -> None:
    """Основная логика работы бота."""
    sent_messages = []
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    clean_messages_date = datetime.today() + timedelta(days=1)
    while True:
        clean_messages_date = clean_error_messages(
            clean_messages_date, sent_messages
        )
        timestamp = logic_for_while_loop(timestamp, bot, sent_messages)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.exception(KEYBOARD_INTERRUPT_TEXT)
