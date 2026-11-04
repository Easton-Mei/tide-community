#!/usr/bin/env python3
"""Allowlist release builder: never includes user state or installed runtimes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
ROOT=Path(__file__).resolve().parents[1]
VERSION='0.2.1'
DIRECTORIES=('app','agent','docs','examples','scripts','tests','.github')
FILES=('README.md','LICENSE','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md','SECURITY.md','AGENTS.md','.gitignore','tide.py','start.sh','启动潮汐.command','启动潮汐.bat','安装 Hermes.command','config/README.md')


def release_files():
    files=[ROOT/name for name in FILES]
    for folder in DIRECTORIES:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
    return sorted(set(files))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist');parser.add_argument('--version',default=VERSION);parser.add_argument('--name',help='Stable archive and top-level folder name for a clean local handoff');args=parser.parse_args()
    if not re.fullmatch(r'[0-9A-Za-z.\-]+', args.version):
        raise SystemExit('Invalid release version')
    prefix=args.name or f'Tide-Community-{args.version}'
    if not re.fullmatch(r'[A-Za-z0-9][0-9A-Za-z.\-]*', prefix):
        raise SystemExit('Invalid archive name')
    args.output.mkdir(parents=True,exist_ok=True)
    archive=args.output/f'{prefix}.zip'
    manifest={}
    with zipfile.ZipFile(archive.with_suffix('.zip.tmp'),'w',zipfile.ZIP_DEFLATED) as output:
        for path in release_files():
            data=path.read_bytes();relative=path.relative_to(ROOT).as_posix()
            if path.suffix not in ('.png','.jpg','.webp'):
                text=data.decode('utf-8')
                if re.search(r'/' + r'Users/[^/\s]+/',text) or re.search(r'gh[pousr]_[A-Za-z0-9]{30,}',text) or ('BEGIN ' + 'PRIVATE KEY') in text:
                    raise SystemExit(f'敏感内容检查未通过：{relative}')
            manifest[relative]=hashlib.sha256(data).hexdigest()
            output.write(path,prefix+'/'+relative)
        output.writestr(prefix+'/MANIFEST.sha256.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive.with_suffix('.zip.tmp').replace(archive)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='utf-8')
    print(json.dumps({'archive':str(archive),'sha256':digest,'files':len(manifest)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
