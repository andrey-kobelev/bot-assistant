from typing import Any
import logging
import os
import sys
import time

from telegram import Bot
from dotenv import load_dotenv
from requests import RequestException
from telegram.error import Unauthorized
import requests

import constants as consts
from exception import (
    NotAuthenticatedError,
    FromDateFormatError,
    EndpointError,
    SendMessageError,
    ApiKeysError,
    NoNewStatus,
    EmptyHomeworksListException,
    InvalidStatusError
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


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    consts.FORMATTER
)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def is_empty_or_none(env_value: Any) -> bool:
    """Вспомогательная функция проверяющая переменную окружения."""
    return env_value == '' or env_value is None


def check_tokens() -> None:
    """
    Проверяет переменные окружения.
    """
    if (
        is_empty_or_none(PRACTICUM_TOKEN)
        or is_empty_or_none(TELEGRAM_TOKEN)
    ):
        raise Exception(consts.ENV_TOKEN_ERROR_TEXT)

    if is_empty_or_none(TELEGRAM_CHAT_ID):
        raise Exception(consts.TG_ID_ERROR_TEXT)


def send_message(bot: Bot, msg: str):
    """
    Для отправки сообщения в телеграм.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, msg)
        logger.debug(f'Сообщение: {msg} - отправлено')
    except Exception as error:
        logger.error(error, exc_info=True)
        raise SendMessageError(str(error))


def check_response(response: dict):
    """Проверяет ответ API на соответствие с документацией."""
    if type(response) is not dict:
        raise TypeError(
            consts.API_TYPE_ERROR_TEXT.format(response=response)
        )

    if (
        consts.HOMEWORKS_KEY not in response
    ):
        raise ApiKeysError(
            f'{consts.MISSING_API_KEY.format(key_name=consts.HOMEWORKS_KEY)}: '
            f'{response}'
        )

    if type(response.get(consts.HOMEWORKS_KEY)) != list:
        raise TypeError(
            consts.VALUE_NOT_LIST_ERROR_TEXT
        )

    if len(response.get(consts.HOMEWORKS_KEY)) == 0:
        raise EmptyHomeworksListException(
            consts.NO_NEW_STATUS_EXC
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
    except requests.RequestException as error:
        raise EndpointError(error)

    if response.status_code == 401:
        raise NotAuthenticatedError(
            response.json().get('message')
        )

    if response.status_code == 400:
        raise FromDateFormatError(
            response.json().get('error').get('error')
        )

    if response.status_code != 200:
        raise EndpointError(
            consts.ENDPOINT_ERROR_TEXT.format(
                status_code=response.status_code
            )
        )
    return response.json()


def parse_status(homework: dict) -> str:
    """
    Извлекает из информации конкретной
    домашней работы статус.
    """
    if consts.HOMEWORK_NAME_KEY not in homework:
        raise KeyError(
            consts.MISSING_API_KEY.format(
                key_name=consts.HOMEWORK_NAME_KEY
            )
        )
    homework_name: str = homework[consts.HOMEWORK_NAME_KEY]
    if homework.get(consts.HOMEWORK_STATUS_KEY) not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'Неожиданный статус домашней работы: '
            f'{homework.get(consts.HOMEWORK_STATUS_KEY)}'
        )
    verdict: str = HOMEWORK_VERDICTS.get(
        homework[consts.HOMEWORK_STATUS_KEY]
    )
    return consts.STATUS_TEXT.format(
        homework_name=homework_name,
        verdict=verdict
    )


def get_from_date(dates: list) -> int:
    """Получить from_date для запроса к API."""
    if len(dates) > 0:
        return max(dates)
    return consts.START_UNIX_TIME


def main() -> None:
    """Основная логика работы бота."""
    try:
        homeworks_dates: list = []
        check_tokens()
    except Exception as error:
        logger.critical(error, exc_info=True)
    else:
        try:
            bot = Bot(token=TELEGRAM_TOKEN)
        except Unauthorized as error:
            logger.critical(error, exc_info=True)
        else:
            while True:
                try:
                    timestamp: int = get_from_date(homeworks_dates)
                    api_data: dict = get_api_answer(timestamp)
                    check_response(api_data)
                    homeworks_dates.append(api_data[consts.CURRENT_DATE_KEY])
                    homework: dict = api_data.get(consts.HOMEWORKS_KEY)[0]
                    message = parse_status(homework)
                    send_message(bot, message)
                except NotAuthenticatedError as error:
                    logger.error(error)
                except FromDateFormatError as error:
                    logger.error(error)
                except EndpointError as error:
                    logger.error(error)
                except TypeError as error:
                    logger.error(error, exc_info=True)
                except ApiKeysError as error:
                    logger.error(error, exc_info=True)
                except EmptyHomeworksListException as error:
                    logger.debug(error)
                except InvalidStatusError as error:
                    logger.error(error, exc_info=True)
                except SendMessageError as error:
                    logger.error(error, exc_info=True)
                except RequestException as error:
                    logger.error(error)
                except NoNewStatus as error:
                    logger.debug(error)
                except Exception as error:
                    logger.error(error, exc_info=True)
                finally:
                    time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt as err:
        logger.error(f'Принудительное завершение программы {err}')
    except SystemExit as err:
        logger.critical(err, exc_info=True)
    except Exception as err:
        logger.critical(err, exc_info=True)
