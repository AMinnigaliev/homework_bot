import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv
from requests import RequestException

from exceptions import AbsenceEnvException, InvalidResponseException

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
            'Отсутствует одна или более из обязательных переменных окружения!',
            exc_info=True,
        )
        raise AbsenceEnvException(
            'Отсутствует одна или более из обязательных переменных окружения'
        )


def send_message(bot, message):
    """
    Функция отправляет сообщение в Telegram чат.
    Чат определяется переменной окружения TELEGRAM_CHAT_ID. Принимает на вход
    два параметра: экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'В телегу отправлено сообщение: {message}')
    except Exception as error:
        logger.error(error, exc_info=True)


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
            ENDPOINT, headers=HEADERS, params=payload
        )
    except RequestException as error:
        logger.error(error, exc_info=True)

    status = homeworks.status_code
    if status == 200:
        return homeworks.json()
    else:
        logger.error('Запрос к API прошёл неудачно!')
        raise RequestException('Запрос к API прошёл неудачно.')


def check_response(response):
    """
    Функция проверяет ответ API.
    Ответ должен соответствовать документации из урока API сервиса
    Практикум.Домашка. В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if type(response) is not dict:
        raise TypeError(
            'В ответе API структура данных не соответствует ожиданиям.'
        )
    if 'homeworks' not in response:
        logger.error('Отсутствие ожидаемого ключа в ответе API!')
        raise InvalidResponseException(
            'Отсутствие ожидаемого ключа в ответе API.'
        )
    if type(response['homeworks']) is not list:
        raise TypeError(
            'В ответе API под ключом `homeworks` данные пришли не в виде'
            ' списка.'
        )


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
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - RETRY_PERIOD

    error_message = ''

    while True:
        start = int(time.time())

        try:
            homeworks = get_api_answer(timestamp)
            check_response(homeworks)
            if len(homeworks['homeworks']) == 0:
                logger.debug('В ответе отсутствуют новые статусы.')
            else:
                for homework in homeworks['homeworks']:
                    message = parse_status(homework)
                    send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if error_message != message:
                send_message(bot, message)
                error_message = message

        timestamp = start
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
