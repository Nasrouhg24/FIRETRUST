from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingestion import PUBLIC, download, fetch_area, ingest_bytes


def main():
    parser = argparse.ArgumentParser(description='FIRETRUST evidence pipeline')
    commands = parser.add_subparsers(dest='command', required=True)
    public = commands.add_parser('fetch-public', help='Download current NASA global 24-hour CSV; no MAP_KEY needed')
    public.add_argument('--sensor', choices=list(PUBLIC), default='viirs')
    area = commands.add_parser('fetch-area')
    area.add_argument('--source', default='VIIRS_SNPP_NRT')
    area.add_argument('--bbox', required=True, help='Use --bbox=-12,27,-1,36 for negative coordinates')
    area.add_argument('--days', type=int, default=1)
    area.add_argument('--start')
    local = commands.add_parser('import-csv')
    local.add_argument('path', type=Path)
    bench = commands.add_parser('benchmark')
    bench.add_argument('labels', type=Path)
    bench.add_argument('--output', type=Path, default=Path('artifacts/benchmark.json'))
    commands.add_parser('verify-evidence')
    commands.add_parser('build-warehouse')
    country=commands.add_parser('fetch-country')
    country.add_argument('country')
    country.add_argument('--start-year',type=int,required=True)
    country.add_argument('--end-year',type=int,required=True)
    country.add_argument('--sensors',nargs='+',default=['modis','viirs-snpp'])
    pilot=commands.add_parser('run-pilot')
    pilot.add_argument('--modis',choices=['T','A'],default='T',help='MODIS input satellite: T=Terra, A=Aqua')
    science=commands.add_parser('science-eval',help='Nested temporal, leave-one-region-out, baselines and interval diagnostics')
    science.add_argument('--output',type=Path,default=Path('artifacts/science-eval.json'))
    transfer=commands.add_parser('transfer-eval')
    transfer.add_argument('--modis',choices=['T','A'],default='A')
    transfer.add_argument('--output',type=Path,default=Path('artifacts/transfer-eval.json'))
    audit=commands.add_parser('audit-pairs')
    audit.add_argument('pairs',type=Path,default=Path('artifacts/pilot-pairs.csv'),nargs='?')
    audit.add_argument('--output',type=Path,default=Path('artifacts/raw-count-audit.json'))
    history=commands.add_parser('fetch-history')
    history.add_argument('--source',required=True)
    history.add_argument('--bbox',required=True)
    history.add_argument('--start',required=True)
    history.add_argument('--end',required=True,help='exclusive UTC date')
    pairs=commands.add_parser('prepare-pairs')
    pairs.add_argument('--region',required=True)
    pairs.add_argument('--bbox',required=True)
    pairs.add_argument('--reference',default='N20')
    pairs.add_argument('--modis',default='T')
    pairs.add_argument('--processing',default='standard',choices=['standard','nrt'])
    pairs.add_argument('--validation-year',type=int,required=True)
    pairs.add_argument('--calibration-year',type=int,required=True)
    pairs.add_argument('--test-year',type=int,required=True)
    pairs.add_argument('--output',type=Path,default=Path('artifacts/pairs.csv'))
    triangulation=commands.add_parser('triangulate')
    triangulation.add_argument('reference',type=Path)
    triangulation.add_argument('--output',type=Path,default=Path('artifacts/triangulation.json'))
    args = parser.parse_args()
    try:
        if args.command == 'fetch-public':
            result = download(PUBLIC[args.sensor], f'NASA FIRMS public {args.sensor} global 24h')
        elif args.command == 'fetch-area':
            result = fetch_area(args.source, args.bbox, args.days, args.start)
        elif args.command == 'import-csv':
            result = ingest_bytes(args.path.read_bytes(), f'local import: {args.path.name}')
        elif args.command == 'benchmark':
            from .science import benchmark
            result = benchmark(args.labels, args.output)
        elif args.command == 'build-warehouse':
            from .warehouse import build_snapshot
            result=build_snapshot()
        elif args.command == 'fetch-country':
            from .countries import fetch_country
            result=fetch_country(args.country,args.start_year,args.end_year,args.sensors)
        elif args.command == 'run-pilot':
            from .pilot import run_pilot
            result=run_pilot(args.modis)
        elif args.command == 'science-eval':
            from .experiments import run_all
            report=run_all(args.output)
            result={'output':str(args.output),'n_pairs':report['n_pairs'],'pairs_sha256':report['pairs_sha256']}
        elif args.command == 'transfer-eval':
            from .pilot import transfer_evaluation
            result=transfer_evaluation(args.modis,output=args.output)
        elif args.command == 'audit-pairs':
            from .validation import audit_reference_pairs
            result=audit_reference_pairs(args.pairs,args.output)
        elif args.command == 'fetch-history':
            from .history import fetch_history
            result=fetch_history(args.source,args.bbox,args.start,args.end)
        elif args.command == 'prepare-pairs':
            from .history import prepare_pairs
            result=prepare_pairs(args.region,args.bbox,args.reference,args.modis,args.processing,args.validation_year,args.calibration_year,args.test_year,args.output)
        elif args.command == 'triangulate':
            from .validation import triangulate
            result=triangulate(args.reference,args.output)
        else:
            import hashlib
            from .ingestion import connect
            with connect() as db:
                batches = db.execute('SELECT id,raw_path FROM batches').fetchall()
            result = {'batches': len(batches), 'failures': [r['id'] for r in batches if not Path(r['raw_path']).exists() or hashlib.sha256(Path(r['raw_path']).read_bytes()).hexdigest() != r['id']]}
            if result['failures']:
                print(json.dumps(result, indent=2))
                raise SystemExit(1)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
