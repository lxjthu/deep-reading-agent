# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_web.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend/dist', 'frontend/dist'), ('.env.example', '.'), ('prompts', 'prompts'), ('new_architecture', 'new_architecture'), ('backend/alembic.ini', 'backend')],
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'sqlalchemy', 'sqlalchemy.dialects.sqlite', 'aiosqlite', 'alembic', 'passlib', 'passlib.handlers.bcrypt', 'bcrypt', 'jose', 'jose.jwt', 'apscheduler', 'apscheduler.schedulers.background', 'apscheduler.triggers.interval', 'email_validator', 'pdfplumber', 'pypdf', 'fitz', 'openai', 'pandas', 'openpyxl', 'tqdm', 'yaml', 'json_repair', 'requests', 'dotenv', 'backend.main', 'backend.cleanup', 'backend.db', 'backend.db.models', 'backend.db.session', 'backend.dimension_seed', 'backend.prompt_service', 'backend.template_seed', 'backend.prompt_registry', 'backend.upload_storage', 'backend.auth', 'backend.routers.admin', 'backend.routers.auth', 'backend.routers.upload', 'backend.routers.filter', 'backend.routers.reading', 'backend.routers.prompts', 'backend.routers.download', 'backend.routers.history', 'backend.routers.compare', 'backend.routers.deploy', 'backend.routers.library', 'backend.routers.references', 'backend.routers.data', 'backend.routers.dimensions', 'backend.services.queue_manager', 'backend.services.deepseek_refs', 'backend.utils.api_key', 'new_architecture.config', 'new_architecture.paper_cache', 'new_architecture.conversation_engine', 'new_architecture.analysis_dimensions'],
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
