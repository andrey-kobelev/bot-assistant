DATE_FORMAT = '%Y-%m-%dT%XZ'
START_UNIX_TIME = 1702137480

HOMEWORKS_KEY = 'homeworks'
CURRENT_DATE_KEY = 'current_date'
HOMEWORK_NAME_KEY = 'homework_name'
HOMEWORK_STATUS_KEY = 'status'
DATE_UPDATED_KEY = 'date_updated'

STATUS_TEXT = 'Изменился статус проверки работы "{homework_name}". {verdict}'

SENT_SUCCESSFULLY = 'The message has been sent successfully.'
MISSING_KEYS_API = 'Missing expected keys in API response. {key_err}'

FORMATTER = '%(asctime)s - %(funcName)s - %(name)s - %(levelname)s - %(message)s'

ENDPOINT_ERROR_TEXT = 'Endpoint error! API status code: {status_code}'
ENV_TOKEN_ERROR_TEXT = 'Token is not correct!'
TG_ID_ERROR_TEXT = 'Environment TG id variable is missing'
SEND_MESSAGE_ERROR_TEXT = 'Send message error!'
API_TYPE_ERROR_TEXT = 'The type from API response is not correct: {response}'
NO_NEW_STATUS_EXC = 'The response not has new status.'
VALUE_NOT_LIST_ERROR_TEXT = """Key's value is not list!"""
MISSING_API_KEY = 'Missing expected key "{key_name}" in API response.'
