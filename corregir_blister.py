#!/usr/bin/env python3
"""Repair browser integration of Classic and the location module on test clone 311."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Instalar reparaciones; sin esta opcion solo comprobar')
    args=parser.parse_args();root=Path(__file__).resolve().parent
    scripts=['reparar_selector_tema.php','reparar_aviso_undefined.php']
    # Validate both known template shapes and destinations before changing either.
    for script in scripts: subprocess.check_call(['php',str(root/script)])
    if args.apply:
        for script in scripts:subprocess.check_call(['php',str(root/script),'--apply'])
    print('Reparacion del navegador aplicada; recargue la pagina.' if args.apply else 'Comprobacion terminada. Use --apply para instalar y limpiar cache.')

if __name__=='__main__':main()
