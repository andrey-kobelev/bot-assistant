import logging
import os
import sys
import time

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


ENV_VARIABLES_NAMES = (
    'TELEGRAM_TOKEN',
    'PRACTICUM_TOKEN',
    'TELEGRAM_CHAT_ID'
)

STATUS = (
    'Изменился статус проверки '
    'работы "{homework_name}". {verdict}'
)

# Тексты для ошибок.
ENV_VARIABLES_ERROR = (
    'Ошибка переменных окружения: {errors}.'
)
SEND_MESSAGE_ERROR = (
    'Ошибка при отправке сообщения: {message}: {error}'
)
API_TYPE_ERROR = 'Некорректный тип ответа API: {response}'
VALUE_NOT_LIST_ERROR = (
    'Значение ключа "{key_name}" '
    'не является списком. Тип ответа API: {response_type}'
)
MISSING_API_KEY_ERROR = (
    'В ответе API отсутствует ожидаемый ключ: {key_name}'
)
API_GET_PARAMETERS_FOR_ERRORS = (
    'Параметры запроса: Endpoint={url}; '
    'Headers={headers}; Params={params}.'
)
NETWORK_ERROR = (
    f'Ошибка сети при отправке GET-запроса: {{error}}'
    f'{API_GET_PARAMETERS_FOR_ERRORS}'
)
API_ANSWER_ERROR = (
    f'Ошибка в ответе API: {{key}}: {{value}}'
    f'{API_GET_PARAMETERS_FOR_ERRORS}'
)
UNKNOWN_API_ERROR = (
    f'Неизвестная ошибка ответа API. Status code: {{status_code}}'
    f'{API_GET_PARAMETERS_FOR_ERRORS}'
)
NOT_CORRECT_STATUS_ERROR = 'Неожиданный статус домашней работы: {status}'

# Тексты для логов
CRITICAL_LOG_FOR_ENV = (
    'Невозможно запустить программу, '
    'проверьте переменные окружения: {errors}'
)
NOT_NEW_STATUS_LOG = 'В ответе отсутствует новый статус: {homework}'
SENT_SUCCESSFULLY_LOG = 'Сообщение: "{message}" - отправлено успешно.'
STANDARD_ERROR_LOG = (
    'Произошла ошибка во время работы бота. '
    'Подробности: {error}'
)

logger = logging.getLogger(__name__)


def check_tokens() -> None:
    """Проверяет переменные окружения."""
    env_errors = [
        env
        for env in ENV_VARIABLES_NAMES
        if globals().get(env) is None or globals().get(env) == ''
    ]
    if env_errors:
        logger.critical(CRITICAL_LOG_FOR_ENV.format(errors=env_errors))
        raise ValueError(ENV_VARIABLES_ERROR.format(errors=env_errors))


def send_message(bot: Bot, message: str) -> bool:
    """Для отправки сообщения в телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SENT_SUCCESSFULLY_LOG.format(message=message))
        return True
    except Exception as error:
        logger.exception(
            SEND_MESSAGE_ERROR.format(message=message, error=error)
        )
        return False


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
    homeworks = response['homeworks']
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
            NETWORK_ERROR.format(error=error, **parameters)
        )
    data_from_api = response.json()
    for key in ('code', 'error'):
        if key in data_from_api:
            raise APIAnswerError(
                API_ANSWER_ERROR.format(
                    value=data_from_api.get(key),
                    key=key,
                    **parameters
                )
            )
    status = response.status_code
    if status != 200:
        raise APIAnswerError(
            UNKNOWN_API_ERROR.format(
                status_code=status,
                **parameters
            )
        )
    return data_from_api


def parse_status(homework: dict) -> str:
    """Извлекает из информации конкретной домашней работы статус."""
    for key in ('homework_name', 'status'):
        if key not in homework:
            raise KeyError(
                MISSING_API_KEY_ERROR.format(
                    key_name=key
                )
            )
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            NOT_CORRECT_STATUS_ERROR.format(status=status)
        )
    return STATUS.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS[status]
    )


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()
    sent_message = ''
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            check_response(api_answer)
            homework = api_answer.get('homeworks')
            if homework:
                if send_message(bot, parse_status(homework[0])):
                    timestamp = api_answer.get('current_date', timestamp)
            else:
                logger.debug(NOT_NEW_STATUS_LOG.format(
                    homework=homework
                ))
        except Exception as error:
            message = STANDARD_ERROR_LOG.format(error=error)
            logger.exception(message)
            if message != sent_message and send_message(bot, message):
                sent_message = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(funcName)s - '
               '%(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{__file__}.log', mode='w'),
            logging.StreamHandler(stream=sys.stdout)
        ]
    )
    main()
