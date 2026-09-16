"""Optional Slack Workflow Builder delivery, without an app token or AI."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

CONFIG = Path(os.environ.get('AMUL_DATA_DIR', str(Path.home() / 'Library/Application Support/AmulStockMonitor'))) / 'slack-webhook.json'


def send(message, config_path=CONFIG):
    if not config_path.exists():
        return False
    try:
        config = json.loads(config_path.read_text())
    except (ValueError, OSError) as exc:
        raise RuntimeError('Slack delivery configuration is unreadable') from exc
    if not isinstance(config, dict):
        raise RuntimeError('Slack delivery configuration is invalid')
    if config.get('enabled') is not True:
        return False
    url = config.get('url')
    if not isinstance(url, str):
        raise RuntimeError('Slack workflow URL is missing')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'hooks.slack.com'
            or not parsed.path.startswith('/triggers/') or parsed.query or parsed.fragment):
        raise RuntimeError('Slack delivery requires an HTTPS hooks.slack.com/triggers URL')
    # Keep the secret URL out of process arguments and logs. Curl reads its
    # configuration from stdin and verifies TLS using macOS's trusted store.
    payload = json.dumps({'message':message},ensure_ascii=True)
    curl_config = '\n'.join(['url = '+json.dumps(url),
                             'header = "Content-Type: application/json"',
                             'data = '+json.dumps(payload)]) + '\n'
    try:
        result = subprocess.run(['/usr/bin/curl','--config','-','--silent','--show-error',
                                 '--proto','=https','--connect-timeout','10','--max-time','25',
                                 '--write-out','\n%{http_code}'], input=curl_config,
                                capture_output=True,text=True,timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Slack workflow request timed out; delivery is unconfirmed') from exc
    if result.returncode:
        raise RuntimeError(f'Slack workflow connection failed (curl {result.returncode})')
    body, _, status = result.stdout.rpartition('\n')
    if status != '200':
        raise RuntimeError(f'Slack workflow returned HTTP {status}')
    if body.strip() == 'ok':
        return True
    try:
        response = json.loads(body)
    except ValueError as exc:
        raise RuntimeError('Slack workflow acknowledgement was not recognized') from exc
    if not isinstance(response, dict) or response.get('ok') is not True:
        raise RuntimeError('Slack did not acknowledge the workflow request')
    return True
