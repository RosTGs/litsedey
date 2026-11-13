#!/usr/bin/env python3
"""Build a local unsigned macOS app; Python runtime stays beside the source."""
from pathlib import Path
import plistlib
import subprocess
import shutil
root=Path(__file__).resolve().parent
bundle=root/'Лицедей.app/Contents'
(bundle/'MacOS').mkdir(parents=True,exist_ok=True)
(bundle/'Resources').mkdir(exist_ok=True)
shutil.copy2(root/'web/brand/litsedey.icns',bundle/'Resources/Litsedey.icns')
with (bundle/'Info.plist').open('wb') as f:
    plistlib.dump(dict(CFBundleName='Лицедей',CFBundleDisplayName='Лицедей · Мастерская персонажей',CFBundleIdentifier='local.kadr.ai-studio',
        CFBundleExecutable='Litsedey',CFBundleIconFile='Litsedey.icns',CFBundlePackageType='APPL',CFBundleShortVersionString='0.4.0',CFBundleVersion='4',NSCameraUsageDescription='Лицедей использует камеру для локальной проверки моргания, взгляда и мимики персонажа. Видео не записывается и не отправляется.',
        NSHighResolutionCapable=True,NSAppTransportSecurity={'NSAllowsLocalNetworking':True,'NSAllowsArbitraryLoads':True}),f)
subprocess.run(['swiftc','-O',str(root/'native.swift'),'-o',str(bundle/'MacOS/Litsedey'),'-framework','AppKit','-framework','WebKit','-framework','AVFoundation'],check=True)
print(root/'Лицедей.app')
