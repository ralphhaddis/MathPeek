#!/usr/bin/env python3
import argparse
import plistlib
import shutil
import subprocess
import time
from pathlib import Path


def build(root: Path, *, clean: bool = False) -> Path:
    app = root / 'build/MathPeek.app'
    (app / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
    resources = app / 'Contents/Resources'
    resources.mkdir(parents=True, exist_ok=True)

    developer_dir = subprocess.check_output(['xcode-select', '-p'], text=True).strip()
    python = Path(developer_dir) / 'usr/bin/python3'
    pillow_site = Path(
        subprocess.check_output(
            [str(python), '-c', 'import site; print(site.getusersitepackages())'],
            text=True,
        ).strip()
    )
    pillow_package = pillow_site / 'PIL'
    if not pillow_package.is_dir():
        raise RuntimeError(
            f'Pillow is not installed for {python}; install Pillow for the selected Xcode Python and rebuild.'
        )

    info = dict(
        CFBundleIdentifier='com.mathpeek.app',
        CFBundleName='MathPeek',
        CFBundleExecutable='MathPeek',
        CFBundlePackageType='APPL',
        CFBundleVersion='1',
        CFBundleShortVersionString='0.1',
        LSUIElement=True,
        NSHighResolutionCapable=True,
        MathPeekPython=str(python),
        NSServices=[
            dict(
                NSMenuItem={'default': 'Preview Clipboard in MathPeek'},
                NSMessage='previewClipboardService',
                NSPortName='MathPeek',
                NSRequiredContext={},
            )
        ],
    )
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    shutil.copy2(root / 'render.py', resources / 'render.py')

    pillow_bundle = resources / 'python'
    if clean and pillow_bundle.exists():
        shutil.rmtree(pillow_bundle)
    if not (pillow_bundle / 'PIL').is_dir():
        shutil.copytree(pillow_package, pillow_bundle / 'PIL')

    subprocess.run(
        [
            'swiftc',
            str(root / 'Main.swift'),
            '-o',
            str(app / 'Contents/MacOS/MathPeek'),
            '-framework',
            'AppKit',
            '-framework',
            'Carbon',
        ],
        check=True,
    )
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    return app


def quit_running_app(bundle_id: str, process_name: str) -> None:
    running = subprocess.run(['pgrep', '-x', process_name], capture_output=True).returncode == 0
    if not running:
        return
    subprocess.run(
        ['osascript', '-e', f'tell application id "{bundle_id}" to quit'],
        capture_output=True,
    )
    for _ in range(20):
        if subprocess.run(['pgrep', '-x', process_name], capture_output=True).returncode != 0:
            return
        time.sleep(0.1)
    subprocess.run(['pkill', '-x', process_name], capture_output=True)
    time.sleep(0.2)


def install(app: Path, dest: Path, *, relaunch: bool = True) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    quit_running_app('com.mathpeek.app', 'MathPeek')

    if shutil.which('rsync'):
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(['rsync', '-a', '--delete', f'{app}/', f'{dest}/'], check=True)
    else:
        subprocess.run(['ditto', str(app), str(dest)], check=True)

    lsregister = Path(
        '/System/Library/Frameworks/CoreServices.framework/Frameworks/'
        'LaunchServices.framework/Support/lsregister'
    )
    if lsregister.is_file():
        subprocess.run([str(lsregister), '-f', str(dest)], capture_output=True)

    if relaunch:
        subprocess.run(['open', str(dest)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='Build (and optionally install/relaunch) MathPeek.app.')
    parser.add_argument('-i', '--install', action='store_true', help='Install to ~/Applications/MathPeek.app and relaunch')
    parser.add_argument('-t', '--test', action='store_true', help='Run check_render.py before installing')
    parser.add_argument('--no-launch', action='store_true', help='With --install, do not relaunch after installing')
    parser.add_argument('--clean', action='store_true', help='Re-copy bundled Python dependencies cleanly')
    parser.add_argument('--dest', type=Path, default=Path.home() / 'Applications/MathPeek.app', help='Custom install destination')
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    app = build(root, clean=args.clean)
    print(f'Built: {app}')

    if args.test:
        python = Path(subprocess.check_output(['xcode-select', '-p'], text=True).strip()) / 'usr/bin/python3'
        subprocess.run([str(python), str(root / 'check_render.py')], check=True)

    if args.install:
        dest = args.dest.expanduser()
        install(app, dest, relaunch=not args.no_launch)
        print(f'Installed: {dest}')
        if not args.no_launch:
            print('Relaunched MathPeek')


if __name__ == '__main__':
    main()
