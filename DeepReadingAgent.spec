# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['extractor', 'parsers', 'smart_literature_filter', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'aiosqlite', 'passlib', 'passlib.handlers.bcrypt', 'bcrypt', 'jose', 'jose.jwt', 'apscheduler', 'apscheduler.schedulers.background', 'apscheduler.schedulers.asyncio', 'apscheduler.triggers.interval', 'email_validator', 'python_multipart', 'multipart', 'pdfplumber', 'pdfminer', 'pdfminer.high_level', 'pdfminer.layout', 'pdfminer.converter', 'pdfminer.pdfinterp', 'pdfminer.pdfpage', 'pdfminer.pdfdocument', 'pdfminer.psparser', 'pdfminer.pdftypes', 'pdfminer.cmapdb', 'pdfminer.encodingdb', 'pdfminer.image', 'pypdf', 'PyPDF2', 'fitz', 'openai', 'httpx', 'pandas', 'openpyxl', 'tqdm', 'yaml', 'json_repair', 'requests', 'dotenv', 'markdown', 'services.ai_template_generator', 'services.crossref_source', 'services.data_portability', 'services.deepseek_refs', 'services.document_parser', 'services.metadata_match_service', 'services.metadata_sources', 'services.openalex_source', 'services.pdf_metadata_extract', 'services.pdf_metadata_llm', 'services.queue_manager', 'translation_pipeline', 'services.card_notes', 'services.markdown_preview', 'services.abstract_translator', 'routers.cards', 'routers.agent', 'routers.library_chat', 'routers.translation']
hiddenimports += collect_submodules('pdfminer')
hiddenimports += collect_submodules('pdfplumber')
hiddenimports += collect_submodules('pypdf')
hiddenimports += collect_submodules('PyPDF2')
hiddenimports += collect_submodules('fitz')
hiddenimports += collect_submodules('openpyxl')


a = Analysis(
    ['run_web.py'],
    pathex=['backend'],
    binaries=[],
    datas=[('frontend/dist', 'frontend/dist'), ('.env.example', '.'), ('prompts', 'prompts'), ('new_architecture', 'new_architecture'), ('backend', 'backend'), ('parsers.py', '.'), ('smart_literature_filter.py', '.'), ('extractor.py', '.'), ('translation_pipeline.py', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DeepReadingAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DeepReadingAgent',
)
