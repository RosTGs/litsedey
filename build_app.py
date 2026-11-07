#!/usr/bin/env python3
"""Build a local unsigned macOS app; Python runtime stays beside the source."""
from pathlib import Path
import plistlib
import subprocess
root=Path(__file__).resolve().parent
bundle=root/'Kadr.app/Contents'
(bundle/'MacOS').mkdir(parents=True,exist_ok=True)
(bundle/'Resources').mkdir(exist_ok=True)
with (bundle/'Info.plist').open('wb') as f:
    plistlib.dump(dict(CFBundleName='Kadr',CFBundleDisplayName='Kadr · AI Model Studio',CFBundleIdentifier='local.kadr.ai-studio',
        CFBundleExecutable='Kadr',CFBundlePackageType='APPL',CFBundleShortVersionString='0.4.0',CFBundleVersion='4',NSCameraUsageDescription='Kadr использует камеру для локальной проверки моргания, взгляда и мимики персонажа. Видео не записывается и не отправляется.',
        NSHighResolutionCapable=True,NSAppTransportSecurity={'NSAllowsLocalNetworking':True,'NSAllowsArbitraryLoads':True}),f)
subprocess.run(['swiftc','-O',str(root/'native.swift'),'-o',str(bundle/'MacOS/Kadr'),'-framework','AppKit','-framework','WebKit','-framework','AVFoundation'],check=True)
print(root/'Kadr.app')
