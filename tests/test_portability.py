import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

class PortableConfiguration(unittest.TestCase):
    def test_resume_does_not_enable_another_checkouts_installation(self):
        import manage
        with tempfile.TemporaryDirectory() as d:
            plist=Path(d)/'agent.plist'
            plist.write_bytes(plistlib.dumps({'ProgramArguments':['python3','/another/checkout/monitor.py']}))
            with patch.object(manage,'PLIST',plist),patch.object(manage,'launch') as launch,patch.object(sys,'argv',['manage.py','resume']):
                with self.assertRaises(RuntimeError): manage.main()
                launch.assert_not_called()

    def test_monitor_reads_the_selected_pin_and_data_directory(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run([sys.executable,'-c','import monitor,json; print(json.dumps([monitor.PIN,str(monitor.DATA)]))'],env=os.environ|{'AMUL_PINCODE':'560001','AMUL_DATA_DIR':d},capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout),['560001',d])

    def test_installed_schedule_retains_configuration_without_shell(self):
        import manage
        with tempfile.TemporaryDirectory() as d:
            plist=Path(d)/'agent.plist'
            def fake_launch(*args,**kwargs):
                return subprocess.CompletedProcess(args,1 if args[0]=='print' else 0,'','')
            with patch.object(manage,'PLIST',plist),patch.object(manage,'DATA',Path(d)/'data'),patch.object(manage,'launch',side_effect=fake_launch),patch.object(sys,'argv',['manage.py','install']),patch.dict(os.environ,{'AMUL_PINCODE':'560001'}):
                manage.main()
            installed=plistlib.loads(plist.read_bytes())
            self.assertEqual(installed['EnvironmentVariables'].get('AMUL_PINCODE'),'560001')
            self.assertEqual(installed['EnvironmentVariables'].get('AMUL_DATA_DIR'),str(Path(d)/'data'))
