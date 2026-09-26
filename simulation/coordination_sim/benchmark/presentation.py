"""Self-contained offline replay fallback for environments forbidding listeners."""
from ..runner import ROOT
from ..serialization import canonical


def export_html(folder,payload):
    page=(ROOT/'ui/index.html').read_text()
    css=(ROOT/'ui/style.css').read_text()
    js=(ROOT/'ui/app.js').read_text()
    data=canonical(payload).decode().replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page=page.replace('<link rel="stylesheet" href="/style.css"><script src="/app.js" defer></script>',
                      '<style>'+css+'</style><script>window.BENCHMARK_DATA='+data+';</script>')
    page=page.replace('</body>','<script>'+js+'</script></body>')
    for name in ('manifest.json','aggregate.json','metric-registry.json','events.csv','company-inspector.json'):
        page=page.replace('/api/artifact?path='+name,name)
    with (folder/'judge.html').open('x',encoding='utf-8') as f:f.write(page)
