#!/usr/bin/env python3
"""No-AI local stock checks and deduplicated macOS notifications."""
import argparse
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from amul_client import AmulClient, CheckError
from slack_alerts import send as send_slack

PIN = os.environ.get('AMUL_PINCODE', '110001')
DATA = Path(os.environ.get('AMUL_DATA_DIR', str(Path.home() / 'Library/Application Support/AmulStockMonitor')))
NOTIFIER = shutil.which('terminal-notifier') or 'terminal-notifier'
PRODUCTS = {
    'rose': {'name':'Rose lassi · pack of 30', 'sku':'LASCP40_30',
             'alias':'amul-high-protein-rose-lassi-200-ml-or-pack-of-30'},
    'plain': {'name':'Plain lassi · pack of 30', 'sku':'LASCP61_30',
              'alias':'amul-high-protein-plain-lassi-200-ml-or-pack-of-30'},
}


def now():
    return datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds')


def classify(product, alias, sku):
    if (not isinstance(product, dict) or product.get('alias') != alias
            or product.get('sku') != sku or str(product.get('publish')) != '1'):
        return {'status':'unknown', 'reason':'Product identity or publication status did not match'}
    available = product.get('available')
    if type(available) not in (int, bool, str) or str(available).lower() not in ('0','1','false','true'):
        return {'status':'unknown', 'reason':'Explicit product availability missing or invalid'}
    return {'status':'available' if str(available).lower() in ('1','true') else 'out_of_stock',
            'name':product.get('name'), 'sku':sku, 'price':product.get('price'),
            'inventory_quantity':product.get('inventory_quantity')}


def process(state, observations, deliver):
    if state.get('pin') not in (None, PIN):
        for key in ('products','consecutive_errors','health_warned','last_error','notification_error'):
            state.pop(key, None)
    delivery_errors = []

    def send(event):
        try:
            deliver(event)
            return True
        except Exception as exc:
            delivery_errors.append(exc)
            return False

    entries = state.setdefault('products', {})
    state['last_check'] = now()
    state['pin'] = PIN
    for key, observation in observations.items():
        entry = entries.setdefault(key, {})
        entry['observation'] = observation
        status = observation['status']
        if status == 'available':
            if entry.get('last_confirmed') != 'available':
                if send({'kind':'restock', 'product':key, **observation}):
                    entry['last_alert'] = now()
                    entry['last_confirmed'] = 'available'
        elif status in ('out_of_stock','not_serviceable'):
            entry['last_confirmed'] = status
        # Unknown must not re-arm an already-delivered availability alert.
    errors = [o.get('reason','Stock could not be verified') for o in observations.values() if o['status'] == 'unknown']
    if errors:
        state['consecutive_errors'] = state.get('consecutive_errors',0) + 1
        state['last_error'] = '; '.join(dict.fromkeys(errors))
        if state['consecutive_errors'] >= 3 and not state.get('health_warned'):
            if send({'kind':'health', 'reason':state['last_error']}):
                state['health_warned'] = True
    else:
        if state.get('health_warned'):
            if send({'kind':'recovery'}):
                state['health_warned'] = False
        state['consecutive_errors'] = 0
        state.pop('last_error',None)
    if delivery_errors:
        raise delivery_errors[0]


def notify(event):
    kind = event['kind']
    group = 'amul-stock-' + event.get('product',kind)
    link = 'https://shop.amul.com/'
    if kind == 'restock':
        product = PRODUCTS[event['product']]
        title = 'Amul lassi is available'
        price = f" · ₹{event['price']}" if event.get('price') is not None else ''
        message = f"{product['name']}{price}. Delivery PIN {PIN}. Click to open Amul."
        link += 'en/product/' + product['alias']
        if send_slack(f'Amul restock alert\n{product["name"]}{price}\nDelivery PIN: {PIN}\nChecked: {now()}\n{link}\nAvailability can change before checkout.'):
            logging.info('Restock submitted to Slack workflow: %s', event['product'])
            return
    elif kind == 'health':
        title, message = 'Amul stock checks need attention', event['reason'][:180] + '. Checks will keep retrying.'
    elif kind == 'recovery':
        title, message = 'Amul stock checks recovered', f'Stock checks for PIN {PIN} are working again.'
    else:
        title, message = 'Amul monitor — test notification', f'Local alerts for PIN {PIN} work. This is a test, not a stock alert.'
    result = subprocess.run([str(NOTIFIER),'-title',title,'-message',message,
                             '-group',group,'-sound','default','-open',link],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Mac notification delivery failed: ' + (result.stderr or result.stdout).strip()[:200])
    logging.info('Notification submitted: %s', kind)


def check():
    observations = {}
    store = None
    try:
        with AmulClient() as client:
            store = client.select_pin(PIN)
            if store is None:
                return {key:{'status':'not_serviceable'} for key in PRODUCTS}, None
            for key, product in PRODUCTS.items():
                try:
                    observations[key] = classify(client.product(product['alias'],store), product['alias'],product['sku'])
                except CheckError as exc:
                    observations[key] = {'status':'unknown','reason':str(exc)}
    except (CheckError, OSError, ValueError) as exc:
        observations = {key:{'status':'unknown','reason':str(exc)} for key in PRODUCTS}
    return observations, store


def save(state):
    target = DATA / 'state.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(state,indent=2,ensure_ascii=False) + '\n')
    temp.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--test-notification',action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    DATA.mkdir(parents=True,exist_ok=True)
    if args.status:
        print((DATA/'state.json').read_text() if (DATA/'state.json').exists() else 'No check has run yet.')
        return 0
    handler = RotatingFileHandler(DATA/'monitor.log',maxBytes=524288,backupCount=2)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    if args.test_notification:
        notify({'kind':'test'})
        print('Test notification submitted to macOS.')
        return 0
    with (DATA/'monitor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            state = json.loads((DATA/'state.json').read_text()) if (DATA/'state.json').exists() else {}
            if not isinstance(state, dict):
                raise ValueError('Invalid state file')
        except ValueError:
            logging.error('State file is unreadable; preserved for diagnosis')
            notify({'kind':'health','reason':'Local state file is unreadable'})
            return 1
        observations, store = check()
        state['store'] = store
        code = 0
        try:
            process(state, observations, notify)
            state.pop('notification_error',None)
        except (RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
            state['notification_error'] = str(exc)[:250]
            logging.error('Notification failed; will retry on next check')
            code = 1
        save(state)
        logging.info('PIN %s store %s: %s',PIN,store.get('alias') if store else None,
                     json.dumps(observations,ensure_ascii=False))
        print(json.dumps({'checked_at':state['last_check'],'pin':PIN,'store':store,'products':observations},ensure_ascii=False))
        return code or int(any(o['status']=='unknown' for o in observations.values()))


if __name__ == '__main__':
    raise SystemExit(main())
