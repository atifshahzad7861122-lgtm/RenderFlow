# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('faster_whisper')


a = Analysis(
    ['F:/yt tool/Rendering Engine By Ai With Atif - Copy/installer/launcher_entry.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['engine', 'engine.ai_gateway', 'engine.canonical_scene_plan', 'engine.openmontage_adapter', 'engine.timeline_validator', 'engine.hardware_detector', 'engine.render_profiles', 'engine.fast_pipeline', 'engine.caption_ass', 'engine.verify_output', 'engine.transcribe', 'engine.stt_provider', 'engine.clip_tokenizer', 'engine.semantic_vision', 'engine.sync_engine_v3', 'engine.visual_analyzer', 'engine.context_analyzer', 'engine.sync_v3_intelligence', 'engine.updater', 'engine.crypto_ed25519', 'engine.updates', 'engine.updates.models', 'engine.updates.semver', 'engine.updates.artifact_verifier', 'engine.updates.manifest_validator', 'engine.updates.download_service', 'engine.updates.installer_launcher', 'engine.updates.post_update_verifier', 'engine.updates.recovery_service', 'engine.updates.update_service', 'web.server', 'uvicorn', 'fastapi', 'ctranslate2', 'faster_whisper', 'onnxruntime', 'regex', 'ftfy', 'psutil'],
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
    name='RenderingStudio_v2.6.0_candidate_v3',
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
    name='RenderingStudio_v2.6.0_candidate_v3',
)
