import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

from exceptions import (
    InvalidResponseException,
    RequestExceptionForTests,
    StatusCodeNot200Exception,
)

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
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
file_handler = RotatingFileHandler(
    'logger.log', maxBytes=50000000, backupCount=5
)
steam_handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
steam_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(steam_handler)


def check_tokens():
    """
    Функция проверяет доступность переменных окружения.
    Эти переменные необходимы для работы программы. Если отсутствует хотя бы
    одна переменная окружения — продолжать работу бота нет смысла.
    """
    if not (PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        logger.critical(
            'Отсутствует одна или более из обязательных переменных окружения!'
        )
        sys.exit(
            'Отсутствует одна или более из обязательных переменных окружения!'
        )


def send_message(bot, message):
    """
    Функция отправляет сообщение в Telegram чат.
    Чат определяется переменной окружения TELEGRAM_CHAT_ID. Принимает на вход
    два параметра: экземпляр класса Bot и строку с текстом сообщения.
    """
    global sended
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'В телегу отправлено сообщение: {message}')
        sended = True
    except telegram.error.TelegramError as error:
        logger.error(error, exc_info=True)
        sended = False


def get_api_answer(timestamp):
    """
    Функция делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка. В случае
    успешного запроса должна вернуть ответ API, приведя его из формата JSON
    к типам данных Python.
    """
    payload = {'from_date': timestamp}
    try:
        homeworks = requests.get(
            ENDPOINT, headers=HEADERS, params=payload,
        )
        status = homeworks.status_code
        if status == HTTPStatus.OK:
            return homeworks.json()
        raise StatusCodeNot200Exception(f'Код ответа API: {status}!')
    except AttributeError as error:
        logger.error(error, exc_info=True)
        raise AttributeError('Переданный API объект не имеет атрибута "json"!')
    except ValueError as error:
        logger.error(error, exc_info=True)
        raise ValueError('Hе удастся десериализовать JSON!')
    except StatusCodeNot200Exception as error:
        logger.error(error, exc_info=True)
        raise
    except requests.RequestException as error:
        logger.error(error, exc_info=True)
        raise RequestExceptionForTests('Запрос к API прошёл неудачно!')
    except Exception as error:
        logger.error(error, exc_info=True)
        raise


def check_response(response):
    """
    Функция проверяет ответ API.
    Ответ должен соответствовать документации из урока API сервиса
    Практикум.Домашка. В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if not isinstance(response, dict):
        message = 'В ответе API структура данных не соответствует ожиданиям.'
        logger.error(message)
        raise TypeError(message)
    if 'homeworks' not in response:
        message = 'Отсутствие ожидаемого ключа в ответе API!'
        logger.error(message)
        raise InvalidResponseException(message)
    if not isinstance(response['homeworks'], list):
        message = 'В ответе API под ключом `homeworks` не список'
        logger.error(message)
        raise TypeError(message)


def parse_status(homework):
    """
    Функция извлекает из конкретной домашней работы статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_VERDICTS.
    """
    try:
        status = homework['status']
        verdict = HOMEWORK_VERDICTS[status]
        homework_name = homework['homework_name']
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError as error:
        logger.error(error, exc_info=True)
        raise KeyError('Отсутствие необходимых данных в ответе API!')


def main():
    """Основная логика работы бота."""
    global correct_data, sended

    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - RETRY_PERIOD

    error_message = ''
    correct_data = True
    sended = True

    while True:
        if correct_data and sended:
            start = int(time.time())

        try:
            homeworks = get_api_answer(timestamp)
            check_response(homeworks)
            if len(homeworks['homeworks']) == 0:
                logger.debug('В ответе отсутствуют новые статусы.')
            else:
                for homework in homeworks['homeworks']:
                    message = parse_status(homework)
                    correct_data = True
                    send_message(bot, message)
        except Exception as error:
            correct_data = False
            message = f'Сбой в работе программы: {error}'
            if error_message != message:
                send_message(bot, message)
                error_message = message

        timestamp = start
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
