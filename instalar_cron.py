#!/usr/bin/env python3
"""Instalar una tarea cada diez minutos, exclusivamente en el clon configurado."""
import argparse
from pathlib import Path
import shlex
import sys
import sync


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    settings=sync.read_json(sync.ROOT/'settings.json')
    sync.bridge(settings,ids=[4480])  # Local IP, DB and shop-domain guards.
    report=sync.ROOT/'reports';report.mkdir(exist_ok=True)
    command=' '.join(shlex.quote(str(x)) for x in ['/usr/bin/timeout','540',sys.executable,sync.ROOT/'sincronizar.py','--apply'])
    text='# ERP -> PrestaShop de pruebas '+sync.test_host(settings)+'\nSHELL=/bin/bash\nPATH=/usr/local/bin:/usr/bin:/bin\n*/10 * * * * root '+command+' >> '+shlex.quote(str(report/'cron.log'))+' 2>&1\n'
    path=Path('/etc/cron.d/mercaboy-precios-pruebas')
    if path.exists() and path.read_text()!=text:
        raise RuntimeError('La tarea existente difiere: revisar antes de sustituir '+str(path))
    print(text,end='')
    if args.apply:
        path.write_text(text);path.chmod(0o644)
        print('Instalado: '+str(path))


if __name__=='__main__':main()
