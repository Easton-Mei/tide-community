#!/usr/bin/env python3
"""Generate a dependency-free, offline-readable Chinese HTML guide."""
from pathlib import Path
import html
import re
ROOT=Path(__file__).resolve().parents[1]
names=['零基础认识潮汐','快速开始','常用操作','Agent安装','常见问题']

def inline(value):
    text=html.escape(value)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\[([^\]]+)\]\((https://[^\s)]+)\)', r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', text)
    return re.sub(r'`([^`]+)`',r'<code>\1</code>',text)

sections=[]
for i,name in enumerate(names):
    content=[];code=[];in_code=False
    for line in (ROOT/'docs'/f'{name}.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            if in_code:content.append('<pre>'+html.escape('\n'.join(code))+'</pre>');code=[]
            in_code=not in_code;continue
        if in_code:code.append(line);continue
        if line.startswith('# '):content.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):content.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:content.append('<p>'+inline(line)+'</p>')
    sections.append(f'<section id="chapter-{i}">'+''.join(content)+'</section>')
nav=''.join(f'<a href="#chapter-{i}">{name}</a>' for i,name in enumerate(names))
page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>潮汐 · 新手使用教程</title><link rel="stylesheet" href="guide.css"></head><body><aside><b>≈ 潮汐 Tide</b><p>从第一次启动，到自己的 Agent。</p><nav>'+nav+'</nav><small>离线教程 · v0.1 · 零基础说明增补版</small></aside><main>'+''.join(sections)+'</main></body></html>'
(ROOT/'docs'/'开始阅读.html').write_text(page,encoding='utf-8')
