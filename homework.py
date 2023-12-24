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
    UnknownAPIAnswerError
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

STATUS_TEXT = (
    'Изменился статус проверки '
    'работы "{homework_name}". {verdict}'
)
SENT_SUCCESSFULLY = 'Сообщение: "{message}" - отправлено успешно.'
MISSING_KEYS_API = 'В ответе API отсутствует ожидаемый ключ. {key_err}'
DATE_FORMAT = '%Y-%m-%dT%XZ'
ENDPOINT_ERROR_TEXT = 'Endpoint error! API status code: {status_code}'
ENV_VARIABLE_ERROR_TEXT = 'Ошибка переменной окружения: {env_value}'
TG_ID_ERROR_TEXT = 'Ошибка id чата телеграмм.'
SEND_MESSAGE_ERROR_TEXT = ('Ошибка при отправке сообщения: '
                           '{message}. Детали: {details}')
API_TYPE_ERROR_TEXT = 'Некорректный тип ответа API: {response}'
NO_NEW_STATUS_EXC = 'Статус не изменился'
VALUE_NOT_LIST_ERROR_TEXT = (
    'Значение ключа "{key_name}" '
    'не является списком. Тип ответа API: {response_type}'
)
MISSING_API_KEY = 'Отсутствует ключ "{key_name}" в ответе API.'
REQUESTS_ERROR_TEXT = (
    'Ошибка сети при отправке GET-запроса!'
    '\nПараметры запроса:'
    '\nEndpoint={endpoint};'
    'Headers={headers};'
    'Params={params}.\n'
    '\nДелали ошибки: {error}'
)

NOT_CORRECT_STATUS = 'Неожиданный статус домашней работы: {status}'

FORMATTER = ('%(asctime)s - %(funcName)s - '
             '%(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format=FORMATTER,
    stream=sys.stdout
)


def check_tokens() -> None:
    """Проверяет переменные окружения."""
    tokens = [
        TELEGRAM_TOKEN,
        PRACTICUM_TOKEN,
        TELEGRAM_CHAT_ID
    ]
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
            f'Ошибка переменной окружения: {error}',
            exc_info=True
        )
        raise


def send_message(bot: Bot, message: str) -> None:
    """Для отправки сообщения в телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SENT_SUCCESSFULLY.format(message=message))
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
            MISSING_API_KEY.format(key_name="homeworks")
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
            REQUESTS_ERROR_TEXT.format(
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
                f'Неизвестная ошибка ответа API. Code: {response.status_code}'
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
                MISSING_API_KEY.format(
                    key_name=key
                )
            )

    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise StatusError(
            NOT_CORRECT_STATUS.format(status=homework.get("status"))
        )

    return STATUS_TEXT.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS.get(
            homework['status']
        )
    )


def get_from_date(api_answer: dict) -> int:
    """Обновляет отсечку времени по присланным данным из API."""
    if 'current_date' not in api_answer:
        raise KeyError(
            MISSING_API_KEY.format(
                key_name='current_date'
            )
        )
    return int(api_answer.get('current_date'))


def send_error_message(bot: Bot, message: str, messages: list):
    """Отправляет в телеграм сообщение ошибки."""
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
            logger.debug(f'В ответе отсутствует новый статус: {homework}')

    except APIAnswerError as error:
        message = f'Ошибка ответа API: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except UnknownAPIAnswerError as error:
        message = f' Неизвестная ошибка ответа API: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except NotAuthenticatedError as error:
        message = f'Проверьте токен API: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except StatusError as error:
        message = f'Неожиданный статус домашней работы: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except TypeError as error:
        message = f'Неожиданный тип ответа API: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except KeyError as error:
        message = f'Отсутствует ожидаемый ключ в ответе API: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    except Exception as error:
        message = f'Неизвестная ошибка: {error}'
        logger.error(message, exc_info=True)
        send_error_message(bot, message, messages)
    else:
        return get_from_date(api_answer)


def main() -> None:
    """Основная логика работы бота."""
    sent_messages = []
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    update_date = datetime.today() + timedelta(days=1)
    while True:
        if datetime.today() == update_date:
            sent_messages.clear()
            update_date = datetime.today() + timedelta(days=1)

        timestamp = logic_for_while_loop(timestamp, bot, sent_messages)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.exception('Принудительное завершение программы.')
