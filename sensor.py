import logging
import json
import datetime

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.const import (STATE_UNAVAILABLE, STATE_UNKNOWN)

_LOGGER = logging.getLogger(__name__)
REQUIREMENTS = ['requests-oauthlib==1.2.0']

DOMAIN = 'bosch_dryer'

CONF_CLIENT_ID = 'client_id'
CONF_REFRESH_TOKEN = 'refresh_token'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CLIENT_ID): cv.string,
    vol.Required(CONF_REFRESH_TOKEN): cv.string,
})

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(minutes=1)
SENSOR_TYPES = ['door', 'program', 'remaining', 'state']
BASE_URL = 'https://api.home-connect.com/'


def _build_api_url(suffix, haId=None):
    base_url = BASE_URL + 'api/'
    if suffix[0] == '/':
        suffix = suffix[1:]
    return base_url + suffix.format(haid=haId)


def _ignore_token_update(token):
    # We need to supply a function to enable automatic usage of refresh tokens
    pass

def setup_platform(hass, config, add_devices, discovery_info=None):
    from requests_oauthlib import OAuth2Session
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry

    _LOGGER.debug("Starting Bosch Dryer sensor")

    client_id = config.get(CONF_CLIENT_ID)
    token = {'access_token': 'XXX',
             'expires_in': -1,
             'refresh_token': config.get(CONF_REFRESH_TOKEN),
             'token_type': 'Bearer'
            }
    session = OAuth2Session(client_id=client_id,
                            token=token,
                            auto_refresh_url=BASE_URL+'security/oauth/token',
                            token_updater=_ignore_token_update)
    retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[500,502,504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    r = session.get(_build_api_url('/homeappliances'))
    appliances = json.loads(r.content)['data']['homeappliances']
    for a in appliances:
        if a['type'] != 'Dryer':
            continue
        haId = a['haId']
        reader = BoschDryerDataReader(session, a['haId'])
        add_devices([BoschDryerSensorEntity(reader,
                                            key,
                                            a['brand'],
                                            a['vib'],
                                            key.capitalize()
                                            )
                     for key in SENSOR_TYPES])


class BoschDryerDataReader:
    def __init__(self, session, haId):
        self._session = session
        self._haId = haId
        self._state = {}

    @property
    def haId(self):
        """ returns the hardware Identifier """
        return self._haId

    def get_data(self, key):
        if key in self._state:
            return self._state[key]
        return STATE_UNKNOWN

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        _LOGGER.debug("Bosch Dryer updating data")

        r = self._session.get(_build_api_url('/homeappliances/{haid}', self._haId))
        s = json.loads(r.content)
        if not s['data']['connected']:
            self._state['state'] = STATE_UNAVAILABLE
            self._state['door'] = STATE_UNKNOWN
            self._state['program'] = STATE_UNKNOWN
            self._state['remaining'] = STATE_UNKNOWN
            return

        r = self._session.get(_build_api_url('/homeappliances/{haid}/status', self._haId))
        s = json.loads(r.content)
        for st in s['data']['status']:
            if st['key'] == 'BSH.Common.Status.DoorState':
                self._state['door'] = st['value'].replace('BSH.Common.EnumType.DoorState.', '').lower()
            elif st['key'] == 'BSH.Common.Status.OperationState':
                self._state['state'] = st['value'].replace('BSH.Common.EnumType.OperationState.', '').lower()
        self._state['remaining'] = STATE_UNKNOWN

        program = STATE_UNKNOWN
        if self._state['state'] not in ['inactive', 'ready']:
            r = self._session.get(_build_api_url('/homeappliances/{haid}/programs/active', self._haId))
            s = json.loads(r.content)
            program = s['data']['key']
            for st in s['data']['options']:
                if st['key'] == 'BSH.Common.Option.RemainingProgramTime':
                    self._state['remaining'] = int(st['value'])
                    assert st['unit'] == 'seconds'
        else:
            r = self._session.get(_build_api_url('/homeappliances/{haid}/programs/selected', self._haId))
            s = json.loads(r.content)
            program = s['data']['key']
        if program:
            self._state['program'] = program.replace('LaundryCare.Dryer.Program.', '').lower()


class BoschDryerSensorEntity(Entity):
    def __init__(self, reader, key, brand, vib, name):
        self._reader = reader
        self._key = key
        self._brand = brand
        self._vib = vib
        self._name = name

    @property
    def unique_id(self):
        return '{}-{}'.format(self._reader.haId, self._name)

    @property
    def name(self):
        return '{} {} {}'.format(self._brand, self._vib, self._name)

    @property
    def state(self):
        return self._reader.get_data(self._key)

    def update(self):
        self._reader.update()
