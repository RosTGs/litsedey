#!/usr/bin/env python3
"""Read-only structural audit of an import PSD or exported model3.json. Python 3.9+."""
import argparse
import json
from pathlib import Path
import sys


def read_json(path):
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=invalid)


def audit(path):
    path = Path(path).expanduser().resolve()
    report = {'path': str(path), 'errors': [], 'warnings': [], 'details': {}}
    errors, warnings, details = report['errors'], report['warnings'], report['details']
    if not path.is_file():
        errors.append('Input file does not exist')
    elif path.suffix.lower() == '.psd':
        try:
            from psd_tools import PSDImage
            psd = PSDImage.open(path)
            details.update(width=psd.width, height=psd.height,
                           depth=psd.depth, color_mode=psd.color_mode.name)
            if psd.depth != 8 or psd.color_mode.name != 'RGB':
                errors.append('PSD import requires RGB, 8 bits/channel')
            names, layers = set(), []
            for layer in psd.descendants():
                if layer.is_group():
                    continue
                item = {'name': layer.name, 'bbox': list(layer.bbox)}
                if layer.name in names:
                    warnings.append('Duplicate layer name: ' + layer.name)
                names.add(layer.name)
                if layer.has_mask():
                    warnings.append('Apply layer mask before import: ' + layer.name)
                im = layer.topil()
                if im is None:
                    warnings.append('No raster pixels: ' + layer.name)
                elif 'A' in im.getbands():
                    item['alpha_extrema'] = list(im.getchannel('A').getextrema())
                    if item['alpha_extrema'][1] == 0:
                        warnings.append('Fully transparent layer: ' + layer.name)
                else:
                    warnings.append('No per-pixel alpha; verify intended opacity: ' + layer.name)
                layers.append(item)
            details['layers'] = layers
            if not layers:
                errors.append('No leaf layers found')
            try:
                merged = psd.topil()
                details['merged_preview_mode'] = merged.mode if merged else None
                if merged is None:
                    warnings.append('Merged preview unavailable; test import in the target editor')
            except Exception as exc:
                errors.append('Merged preview cannot be decoded: ' + str(exc))
            warnings.append('Color profile, visual alignment and target editor import require manual verification')
        except ImportError:
            errors.append('PSD audit requires Pillow and psd-tools in this Python environment')
        except Exception as exc:
            errors.append('PSD read failed: ' + str(exc))
    elif path.name.lower().endswith('.model3.json'):
        try:
            model = read_json(path)
            if not isinstance(model, dict):
                raise ValueError('model3.json must be an object')
            refs = model.get('FileReferences')
            if not isinstance(refs, dict):
                raise ValueError('FileReferences must be an object')
            if model.get('Version') != 3:
                warnings.append('Expected model settings Version 3; check target compatibility')
            if not isinstance(refs.get('Moc'), str) or not refs.get('Moc'):
                errors.append('FileReferences.Moc must be a nonempty string')
            textures = refs.get('Textures')
            if not isinstance(textures, list) or not textures:
                errors.append('FileReferences.Textures must be a nonempty array')
            found = []

            def check_file(label, value):
                if not isinstance(value, str) or not value.strip():
                    errors.append(label + ' must be a nonempty file path')
                    return
                relative = Path(value.replace('\\', '/'))
                target = (path.parent / relative).resolve()
                if relative.is_absolute() or not target.is_relative_to(path.parent):
                    errors.append(label + ' is outside the export folder')
                    return
                found.append({'field': label, 'file': value})
                if not target.is_file() or target.stat().st_size == 0:
                    errors.append(label + ': missing or empty file ' + value)
                elif target.suffix.lower() == '.json':
                    try:
                        if not isinstance(read_json(target), dict):
                            raise ValueError('expected JSON object')
                    except (ValueError, OSError) as exc:
                        errors.append(label + ': invalid JSON: ' + str(exc))

            for key in ('Moc', 'Physics', 'Pose', 'DisplayInfo', 'UserData', 'MotionSync', 'ParameterController'):
                if key in refs:
                    check_file(key, refs[key])
            if isinstance(textures, list):
                for i, value in enumerate(textures):
                    check_file('Textures[%d]' % i, value)
            expressions = refs.get('Expressions', [])
            if not isinstance(expressions, list):
                errors.append('Expressions must be an array')
            else:
                for i, entry in enumerate(expressions):
                    check_file('Expressions[%d].File' % i, entry.get('File') if isinstance(entry, dict) else None)
            motions = refs.get('Motions', {})
            if not isinstance(motions, dict):
                errors.append('Motions must be an object of arrays')
            else:
                for group, entries in motions.items():
                    if not isinstance(entries, list):
                        errors.append('Motion group must be an array: ' + group)
                        continue
                    for i, entry in enumerate(entries):
                        label = 'Motions.%s[%d]' % (group, i)
                        check_file(label + '.File', entry.get('File') if isinstance(entry, dict) else None)
                        if isinstance(entry, dict) and 'Sound' in entry:
                            check_file(label + '.Sound', entry['Sound'])
            known = {'Moc','Textures','Physics','Pose','DisplayInfo','UserData','MotionSync',
                     'ParameterController','Expressions','Motions'}
            for key in refs.keys() - known:
                warnings.append('Unrecognized FileReferences field; inspect manually: ' + key)
            details['references'] = found
            warnings.append('Binary MOC3 validity, texture decoding, rig quality and runtime compatibility are not tested')
        except (ValueError, OSError) as exc:
            errors.append('Model settings read failed: ' + str(exc))
    else:
        errors.append('Supported audit inputs: .psd or .model3.json')
    report['ok'] = not errors
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    result = audit(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
