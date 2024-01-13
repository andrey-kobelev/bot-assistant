import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from telegram import Bot
from dotenv import load_dotenv
import requests

from exceptions import APIAnswerError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

STATUS_TEXT = (
    'Изменился статус проверки '
    'работы "{homework_name}". {verdict}'
)

# Тексты для ошибок.
ENV_VALUE_ERROR = (
    'Некорректное значение переменной '
    'окружения: {env_name}={value}'
)
SEND_MESSAGE_ERROR = (
    'Ошибка при отправке сообщения: {message}'
)
API_TYPE_ERROR = 'Некорректный тип ответа API: {response}'
VALUE_NOT_LIST_ERROR = (
    'Значение ключа "{key_name}" '
    'не является списком. Тип ответа API: {response_type}'
)
MISSING_API_KEY_ERROR = (
    'В ответе API отсутствует ожидаемый ключ: {key_name}'
)
GET_API_ANSWER_ERROR = ("""
Параметры запроса:
Endpoint={url};
Headers={headers};
Params={params}.
""")
NETWORK_ERROR = 'Ошибка сети при отправке GET-запроса!'
UNKNOWN_API_ERROR = 'Неизвестная ошибка ответа API. Code: {status_code}'
NOT_CORRECT_STATUS_ERROR = 'Неожиданный статус домашней работы: {status}'

# Тексты для логов
CRITICAL_LOG_FOR_ENV = (
    'Невозможно запустить программу, '
    'проверьте переменную окружения: {env_name}'
)
NOT_NEW_STATUS_LOG = 'В ответе отсутствует новый статус: {homework}'
SENT_SUCCESSFULLY_LOG = 'Сообщение: "{message}" - отправлено успешно.'
STANDARD_ERROR_LOG = ("""
Произошла ошибка во время работы бота.
Подробности:
{error}
""")

logger = logging.getLogger(__name__)
handler = RotatingFileHandler(
    'homework.log', maxBytes=50000000, backupCount=5
)
logger.addHandler(handler)


def check_tokens() -> None:
    """Проверяет переменные окружения."""
    env_variables_names = (
        'TELEGRAM_TOKEN',
        'PRACTICUM_TOKEN',
        'TELEGRAM_CHAT_ID'
    )
    for env_name in env_variables_names:
        try:
            value = globals()[env_name]
            if value is None or value == '':
                raise ValueError(
                    ENV_VALUE_ERROR.format(
                        env_name=env_name,
                        value=value
                    )
                )
        except KeyError:
            logger.critical(
                CRITICAL_LOG_FOR_ENV.format(env_name=env_name),
                exc_info=True
            )
            raise
        except ValueError:
            logger.critical(
                CRITICAL_LOG_FOR_ENV.format(env_name=env_name),
                exc_info=True
            )
            raise


def send_message(bot: Bot, message: str) -> None:
    """Для отправки сообщения в телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SENT_SUCCESSFULLY_LOG.format(message=message))
    except Exception as error:
        logger.error(
            f'{SEND_MESSAGE_ERROR.format(message=message)}'
            f'{error}',
            exc_info=True
        )


def check_response(response: dict) -> None:
    """Проверяет ответ API на соответствие с документацией."""
    if not isinstance(response, dict):
        raise TypeError(
            API_TYPE_ERROR.format(response=type(response))
        )

    if 'homeworks' not in response:
        raise KeyError(
            MISSING_API_KEY_ERROR.format(key_name="homeworks")
        )

    homeworks = response.get('homeworks')

    if not isinstance(homeworks, list):
        raise TypeError(
            VALUE_NOT_LIST_ERROR.format(
                key_name='homeworks',
                response_type=type(homeworks)
            )
        )


def get_api_answer(timestamp: int) -> dict:
    """
    Отправляет запрос к API.
    Возвращает ответ API.
    """
    parameters = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )

    try:
        response = requests.get(
            **parameters
        )
    except requests.exceptions.RequestException as error:
        raise ConnectionError(
            f'{NETWORK_ERROR} '
            f'{GET_API_ANSWER_ERROR.format(**parameters)} '
            f'{error}'
        )

    data_from_api = response.json()
    api_keys = ('code', 'error')
    for key in api_keys:
        if key in data_from_api:
            error_message = ''
            for error_data in tuple(data_from_api.items()):
                error_message += f'{error_data[0].title()}: {error_data[1]} '
            raise APIAnswerError(
                f'{error_message}'
                f'{GET_API_ANSWER_ERROR.format(**parameters)}'
            )

    status = response.status_code

    if status != 200:
        raise APIAnswerError(
            f'{UNKNOWN_API_ERROR} Status code: {status}.'
            f'{GET_API_ANSWER_ERROR.format(**parameters)}'
        )
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
                MISSING_API_KEY_ERROR.format(
                    key_name=key
                )
            )
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            NOT_CORRECT_STATUS_ERROR.format(status=homework_status)
        )

    return STATUS_TEXT.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS.get(
            homework_status
        )
    )


def main() -> None:
    """Основная логика работы бота."""
    sent_message = ''
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            check_response(api_answer)
            homework = api_answer.get('homeworks')

            if len(homework) > 0:
                send_message(bot, parse_status(homework[0]))
                timestamp = api_answer.get('current_date')
            else:
                logger.debug(NOT_NEW_STATUS_LOG.format(
                    homework=homework
                ))
        except Exception as error:
            message = STANDARD_ERROR_LOG.format(error=error)
            logger.exception(message)
            if message != sent_message:
                send_message(bot, message)
                sent_message = message

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(funcName)s - '
               '%(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    main()
