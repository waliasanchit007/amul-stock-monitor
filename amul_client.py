"""Read Amul's public storefront using a fresh, anonymous regional session."""
import hashlib
import json
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

BASE = 'https://shop.amul.com'
STORE_ID = '62fa94df8c13af2e242eba16'


class CheckError(RuntimeError):
    pass


class AmulClient:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='amul-stock-')
        self.jar = Path(self.temp.name) / 'cookies.txt'
        self.session = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.temp.cleanup()

    def request(self, path, data=None, signed=True):
        headers = {'accept':'application/json, text/plain, */*', 'frontend':'1',
                   'base_url': BASE + '/en/browse/protein',
                   'referer': BASE + '/en/browse/protein', 'cache-control':'no-cache'}
        if signed:
            token = self.session.get('tid')
            if not isinstance(token, str) or not token:
                raise CheckError('Anonymous session token missing')
            timestamp, nonce = str(int(time.time()*1000)), str(secrets.randbelow(1000))
            digest = hashlib.sha256(f'{STORE_ID}:{timestamp}:{nonce}:{token}'.encode()).hexdigest()
            headers['tid'] = f'{timestamp}:{nonce}:{digest}'
        command = ['/usr/bin/curl','-g','-sS','--connect-timeout','10','--max-time','25',
                   '--proto','=https','-b',str(self.jar),'-c',str(self.jar)]
        for key, value in headers.items():
            command.extend(['-H',f'{key}: {value}'])
        if data is not None:
            command.extend(['-X','PUT','-H','content-type: application/json','--data',json.dumps({'data':data})])
        command.extend(['-w','\n%{http_code}',BASE + path])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            raise CheckError('Amul request timed out') from exc
        if result.returncode:
            raise CheckError(f'Amul connection failed (curl {result.returncode})')
        body, _, status = result.stdout.rpartition('\n')
        if status != '200':
            raise CheckError(f'Amul returned HTTP {status}')
        return body

    @staticmethod
    def json_body(body):
        try:
            value = json.loads(body)
        except (ValueError, TypeError) as exc:
            raise CheckError('Amul returned a non-JSON response') from exc
        if not isinstance(value, dict):
            raise CheckError('Amul response structure changed')
        return value

    def refresh_session(self):
        body = self.request(f'/user/info.js?_v={int(time.time()*1000)}', signed=False)
        if not body.strip().startswith('session = '):
            raise CheckError('Amul session response structure changed')
        self.session = self.json_body(body.strip()[len('session = '):].rstrip(';'))

    def select_pin(self, pin):
        self.request('/en/browse/protein', signed=False)
        self.refresh_session()
        # Match the storefront's bracket query encoding; JSON filters returned
        # errors in a manual probe of this deployment.
        query = urlencode({'limit':50, 'filters[0][field]':'pincode',
                           'filters[0][value]':pin, 'filters[0][operator]':'regex',
                           'cf_cache':'1h'}, safe='[]')
        data = self.json_body(self.request('/entity/pincode?' + query))
        records = data.get('records')
        if not isinstance(records, list):
            raise CheckError('PIN lookup did not return a records list')
        exact = [r for r in records if isinstance(r, dict) and str(r.get('pincode')) == pin]
        if not exact:
            if records:
                raise CheckError('PIN lookup returned other PIN codes')
            return None
        raw_stores = [r.get('substore') for r in exact]
        if not all(isinstance(s, str) and s for s in raw_stores):
            raise CheckError('PIN lookup returned an invalid regional store')
        stores = set(raw_stores)
        if len(stores) != 1:
            raise CheckError('PIN lookup returned an ambiguous regional store')
        store = next(iter(stores))
        response = self.request('/entity/ms.settings/_/setPreferences', data={'store':store})
        if response.strip() != 'Updated successfully':
            raise CheckError('Amul did not acknowledge regional store selection')
        self.refresh_session()
        selected = self.session.get('substore', {})
        if not isinstance(selected, dict) or selected.get('alias') != store or not selected.get('_id'):
            raise CheckError('Amul did not retain the selected regional store')
        return {'pin':pin, 'alias':store, 'id':selected['_id'], 'name':selected.get('name',store)}

    def product(self, alias, store):
        query = urlencode({'q':json.dumps({'alias':alias}, separators=(',',':')),
                           'limit':1, 'substore':store['id'], 'v':6, 'device_type':'other'})
        data = self.json_body(self.request('/api/1/entity/ms.products?' + query))
        records = data.get('data')
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise CheckError('Exact product was not returned by Amul')
        return records[0]
