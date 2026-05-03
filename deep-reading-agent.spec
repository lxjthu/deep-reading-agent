# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Deep Reading Agent — Windows single-file executable."""

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend/dist'),
        ('.env.example', '.'),
        ('requirements.txt', '.'),
        ('prompts', 'prompts'),
        ('paddleocr_extractor', 'paddleocr_extractor'),
        ('new_architecture', 'new_architecture'),
        ('paddleocr_pipeline.py', '.'),
        ('paddleocr_local.py', '.'),
        ('parsers.py', '.'),
        ('smart_literature_filter.py', '.'),
    ],
    hiddenimports=[
        # Uvicorn
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # FastAPI & ecosystem
        'fastapi',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'aiosqlite',
        'alembic',
        'passlib',
        'passlib.handlers.bcrypt',
        'bcrypt',
        'jose',
        'jose.jwt',
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.triggers.interval',
        'email_validator',
        # Gradio
        'gradio',
        # PDF extraction
        'pdfplumber',
        'pypdf',
        'fitz',  # PyMuPDF
        # LLM & data
        'openai',
        'pandas',
        'openpyxl',
        'tqdm',
        'yaml',  # PyYAML
        'json_repair',
        'requests',
        'dotenv',  # python-dotenv
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DeepReadingAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
