import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from coordination_sim.benchmark.generation import generate, second_tenant_probe
from coordination_sim.benchmark.runner import run
from coordination_sim.benchmark.service import handler_for
from coordination_sim.benchmark.trace import Trace
from coordination_sim.benchmark.workspaces import SimulatedWorkspace


class ServicePrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.path=run()

    def request(self,path):
        # Execute the actual request handler over in-memory streams; no socket.
        Handler=handler_for(self.path)
        handler=object.__new__(Handler);handler.path=path;handler.wfile=io.BytesIO()
        handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        handler.do_GET()
        return handler.send_response.call_args.args[0],handler.wfile.getvalue()

    def test_http_routes_and_path_boundary_without_listener(self):
        for route in ('/','/app.js','/style.css','/api/run','/api/artifact?path=manifest.json'):
            self.assertEqual(self.request(route)[0],200)
        self.assertEqual(self.request('/api/artifact?path=../../STATUS.md')[0],404)
        self.assertEqual(self.request('/api/artifact?path=/etc/passwd')[0],404)
        self.assertEqual(self.request('/not-a-route')[0],404)

    def test_reset_preserves_the_served_scenario_set(self):
        combined=run(cases=('A','B','portfolio'))
        Handler=handler_for(combined)
        handler=object.__new__(Handler);handler.path='/api/reset-run';handler.wfile=io.BytesIO();handler.rfile=io.BytesIO(b'{}')
        handler.headers={'Origin':None,'Host':'127.0.0.1:8765','Content-Length':'2'}
        handler.server=SimpleNamespace(server_port=8765)
        handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        with patch('coordination_sim.benchmark.service.run',return_value=combined) as rerun:
            handler.do_POST()
        self.assertEqual(handler.send_response.call_args.args[0],200)
        rerun.assert_called_once_with(preset='tiny',seed=17,cases=('A','B','portfolio'))

    def test_tenant_collision_is_denied_without_existence_leak(self):
        s=generate();other=second_tenant_probe();trace=Trace('t',s.company)
        w=SimulatedWorkspace('sharepoint',other,trace)
        args=dict(fields=('excerpt',),now=s.company.anchor)
        denied=w.read(s.company.company_id,'coordinator',('incident-brief-v1',),**args)
        missing=w.read(s.company.company_id,'coordinator',('absent',),**args)
        self.assertEqual(denied,missing);self.assertEqual(denied.records,())
        allowed=w.read(other.company.company_id,'coordinator',('incident-brief-v1',),**args)
        self.assertEqual(allowed.status,'OK')

    def test_offline_artifact_injection_safety_and_captured_pov(self):
        page=(self.path/'judge.html').read_text()
        self.assertIn('window.BENCHMARK_DATA=',page)
        self.assertNotIn('<script src="/app.js"',page)
        data=json.loads((self.path/'judge-data.json').read_text())
        for case in data['cases']:
            p=next(p for p in case['methods']['product_replay']['projections'] if p['viewer_id']=='e0008')
            text=json.dumps(p)
            self.assertNotIn('SSO',text);self.assertNotIn('incident-declaration-v1',text)
            self.assertNotIn('ground_truth',text);self.assertNotIn('expected_classification',text)
        from coordination_sim.benchmark.presentation import export_html
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory(dir=self.path) as d:
            export_html(Path(d),{'malicious':'</script><script>alert(1)</script>'})
            self.assertNotIn('</script><script>alert(1)',(Path(d)/'judge.html').read_text())
