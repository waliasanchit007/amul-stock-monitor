import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess


class SlackAlerts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('slack_alerts'), 'Slack delivery is not implemented')
        import slack_alerts
        self.s = slack_alerts

    def test_no_config_preserves_mac_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(self.s.send('Test', Path(d)/'missing.json'))

    def test_only_slack_workflow_urls_are_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'
            p.write_text(json.dumps({'enabled':True,'url':'https://example.com/triggers/secret'}))
            with self.assertRaises(RuntimeError): self.s.send('Test',p)

    def test_explicit_acknowledgement_and_secret_not_in_command_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';url='https://hooks.slack.com/triggers/test-secret'
            p.write_text(json.dumps({'enabled':True,'url':url}))
            def fake_run(command, **kwargs):
                self.assertNotIn(url,' '.join(command))
                self.assertIn(url,kwargs['input'])
                self.assertIn('Rose lassi',kwargs['input'])
                return subprocess.CompletedProcess(command,0,'{"ok":true}\n200','')
            with patch.object(self.s.subprocess,'run',side_effect=fake_run):
                self.assertTrue(self.s.send('Rose lassi is available',p))

    def test_slack_error_does_not_count_as_delivered(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'
            p.write_text(json.dumps({'enabled':True,'url':'https://hooks.slack.com/triggers/test-secret'}))
            with patch.object(self.s.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"ok":false}\n200','')):
                with self.assertRaises(RuntimeError): self.s.send('Test',p)

    def test_successful_slack_restock_skips_mac_delivery(self):
        import monitor
        with patch.object(monitor,'send_slack',return_value=True), patch.object(monitor.subprocess,'run') as run:
            monitor.notify({'kind':'restock','product':'rose','price':900})
            run.assert_not_called()

    def test_health_and_setup_notifications_never_go_to_slack(self):
        import monitor
        for event in [{'kind':'health','reason':'Check failed'}, {'kind':'recovery'}, {'kind':'test'}]:
            with patch.object(monitor,'send_slack') as send, patch.object(monitor.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')):
                monitor.notify(event)
                send.assert_not_called()

    def test_unavailable_and_unknown_products_never_emit_restock_messages(self):
        import monitor
        state={};events=[]
        for _ in range(4):
            monitor.process(state, {'rose':{'status':'out_of_stock'},'plain':{'status':'unknown','reason':'Check failed'}},events.append)
        self.assertNotIn('restock',[event['kind'] for event in events])
