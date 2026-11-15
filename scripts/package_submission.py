"""Package explicit source/evidence paths; exclude raw data, runtimes, keys and Git."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile


def main():
    root=Path(__file__).resolve().parents[1]
    singles=['README.md','FIRETRUST_Blueprint_2026.md','pyproject.toml','requirements.lock.txt','.gitignore','.gitattributes','.env.example',
             'frontend/package.json','frontend/package-lock.json','frontend/tsconfig.json','frontend/vite.config.ts','frontend/playwright.config.ts','frontend/index.html']
    folders=['backend/firetrust','frontend/src','frontend/public','frontend/dist','frontend/e2e','tests','scripts','docs']
    files={root/name for name in singles}
    for folder in folders:
        files.update(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    output=root/'artifacts'/'FIRETRUST_submission.zip';output.parent.mkdir(exist_ok=True)
    with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=7) as archive:
        for path in sorted(files):
            if not path.exists():raise RuntimeError(f'Package input missing: {path}')
            archive.write(path,path.relative_to(root).as_posix())
    report={'path':str(output.relative_to(root)),'files':len(files),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'excluded':['data','node_modules','.runtime','.git','.env','artifacts except this archive']}
    (output.parent/'submission-package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
