"""Pruebas con ZIP sintéticos: nunca ejecutan el código que contienen."""
from pathlib import Path
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'script.sh'


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'entrada con espacios.zip'
        self.dest = self.root / 'salida con espacios'
        self.scratch = self.root / 'temporales'
        self.scratch.mkdir()
        self.env = {**os.environ, 'TMPDIR': str(self.scratch)}

    def create_zip(self, entries):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, data in entries:
                archive.writestr(name, data)

    def run_script(self, *args):
        result = subprocess.run(
            ['bash', str(SCRIPT), *map(str, args)], cwd=self.root,
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(list(self.scratch.iterdir()), [], 'No se limpiaron los temporales')
        return result

    def run_ok(self):
        before = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        result = self.run_script(self.archive, self.dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(), before)
        return result.stdout

    def test_exact_argument_validation(self):
        for args in ((), ('uno',), ('uno', 'dos', 'tres')):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.strip(),
                                 'Uso: ./script.sh <archivo.zip> <directorio_destino>')

    def test_missing_corrupt_wrong_extension_and_empty_destination(self):
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.archive.write_text('esto no es un ZIP')
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertFalse(self.dest.exists())
        self.create_zip([('a.txt', 'hola')])
        self.assertEqual(self.run_script(self.archive, '').returncode, 1)
        other = self.root / 'entrada.txt'
        shutil.copyfile(self.archive, other)
        self.assertEqual(self.run_script(other, self.dest).returncode, 1)

    def test_extensions_metadata_and_exact_audit_lines(self):
        entries = [
            ('src/main.py', 'from PySide6.QtWidgets import QWidget\nprint("PySide6")\n'),
            ('src/OTHER.PY', 'print("no")\n'),
            ('docs/a.TXT', 'texto'), ('README', 'sin extensión'),
            ('.env', 'oculto'), ('.config.json', '{}'), ('final.', 'sin extensión'),
            ('linea\nnueva.txt', 'salto'), ('-opcion.txt', 'guion'),
            ('__MACOSX/src/._main.py', 'PySide6 no debe buscarse'),
            ('src/.DS_Store', 'metadatos'), ('src/._datos', 'metadatos'),
            ('Images/foto.JPG', b'contenido de prueba'),
        ]
        self.create_zip(entries)
        output = self.run_ok()
        self.assertTrue((self.dest / 'py/src/main.py').is_file())
        self.assertTrue((self.dest / 'py/src/OTHER.PY').is_file())
        self.assertTrue((self.dest / 'json/.config.json').is_file())
        for name in ('README', '.env', 'final.'):
            self.assertTrue((self.dest / 'sin_extension' / name).is_file())
        for name in ('docs/a.TXT', 'linea\nnueva.txt', '-opcion.txt'):
            self.assertTrue((self.dest / 'txt' / name).is_file())
        self.assertTrue((self.dest / 'jpg/Images/foto.JPG').is_file())
        for name in ('__MACOSX/src/._main.py', 'src/.DS_Store', 'src/._datos'):
            self.assertTrue((self.dest / 'metadatos_macos' / name).is_file())
        self.assertIn('1:from PySide6.QtWidgets import QWidget', output)
        self.assertIn('2:print("PySide6")', output)
        self.assertIn('Archivo: ' + str(self.dest / 'py/src/OTHER.PY') + '\nContiene PySide6: no', output)
        self.assertNotIn('PySide6 no debe buscarse', output)
        self.assertIn('Archivos de contenido organizados: 10\n', output)
        self.assertIn('Metadatos macOS separados: 3\n', output)
        self.assertIn('Archivos .py analizados: 2\n', output)
        self.assertIn('Archivos con menciones de PySide6: 1\n', output)
        self.assertIn('Archivos con importaciones de PySide6 detectadas: 1\n', output)
        self.assertEqual(len([p for p in self.dest.rglob('*') if p.is_file()]), len(entries))

    def test_case_insensitive_boundaries_and_comment_vs_import(self):
        self.create_zip([
            ('comentario.py', '# PySide6 en un comentario\n'),
            ('minusculas.py', 'from pyside6.QtWidgets import QWidget\n'),
            ('lista.py', 'import sys, PySide6.QtCore as qt\n'),
            ('simple.py', 'import PySide6\nimport PySide6.QtGui\n'),
            ('no.py', 'from PyQt6 import QtWidgets\n# PyQR cv2 MyPySide6 PySide6_extra\n'),
        ])
        output = self.run_ok()
        self.assertIn('Archivos .py analizados: 5\n', output)
        self.assertIn('Archivos con menciones de PySide6: 4\n', output)
        self.assertIn('Archivos con importaciones de PySide6 detectadas: 3\n', output)
        self.assertIn('No se detectaron importaciones de PySide6.', output)

    def test_only_pyside6_is_counted_not_other_qt_libraries(self):
        self.create_zip([
            ('pyside6_real.py', 'from PySide6.QtWidgets import QWidget\n'),
            ('PySide6_solo_nombre.py', 'from PyQt6.QtWidgets import QWidget\n'),
            ('otras.py', 'import PyQt5\nimport PySide2\nimport PySide60\n'),
            ('parecidas.py', 'import PySide6_extra\nimport MyPySide6\n'),
        ])
        output = self.run_ok()
        self.assertIn('Archivos .py analizados: 4\n', output)
        self.assertIn('Archivos con menciones de PySide6: 1\n', output)
        self.assertIn('Archivos con importaciones de PySide6 detectadas: 1\n', output)
        self.assertEqual(output.count('Contiene PySide6: sí'), 1)
        self.assertEqual(output.count('Contiene PySide6: no'), 3)

    def test_equal_filenames_keep_relative_paths(self):
        self.create_zip([('uno/a.py', 'import PySide6\n'), ('dos/a.py', 'print(1)\n')])
        output = self.run_ok()
        self.assertEqual((self.dest / 'py/uno/a.py').read_text(), 'import PySide6\n')
        self.assertEqual((self.dest / 'py/dos/a.py').read_text(), 'print(1)\n')
        self.assertIn('Archivos .py analizados: 2\n', output)

    def test_existing_nonempty_destination_and_repeated_run_are_rejected(self):
        self.create_zip([('a.txt', 'nuevo')])
        self.dest.mkdir()
        keep = self.dest / 'existente.txt'
        keep.write_text('original')
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertEqual(keep.read_text(), 'original')
        self.assertEqual(list(self.dest.iterdir()), [keep])
        keep.unlink()
        self.run_ok()
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertEqual((self.dest / 'txt/a.txt').read_text(), 'nuevo')

    def test_existing_empty_destination_is_accepted(self):
        self.dest.mkdir()
        self.create_zip([('a.txt', 'hola')])
        self.run_ok()

    def test_file_or_symlink_destination_is_rejected(self):
        self.create_zip([('a.txt', 'nuevo')])
        self.dest.write_text('original')
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertEqual(self.dest.read_text(), 'original')
        self.dest.unlink()
        outside = self.root / 'fuera'
        outside.mkdir()
        self.dest.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.run_script(self.archive, str(self.dest) + '/').returncode, 1)
        self.assertEqual(list(outside.iterdir()), [])

    def test_empty_zip(self):
        self.create_zip([])
        output = self.run_ok()
        self.assertIn('Archivos .py analizados: 0\n', output)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_zip_without_python(self):
        self.create_zip([('datos.csv', 'a,b\n1,2\n')])
        self.assertIn('Archivos .py analizados: 0\n', self.run_ok())

    def test_unsafe_paths_are_rejected(self):
        for name in ('../escape', '/escape', 'C:/escape', 'a/../../escape', 'a\\escape'):
            with self.subTest(name=name):
                self.create_zip([('bueno.txt', 'bueno'), (name, 'malo')])
                self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.root / 'escape').exists())

    def test_symlinks_in_zip_are_rejected(self):
        link = zipfile.ZipInfo('enlace')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.create_zip([(link, '../fuera')])
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertFalse(self.dest.exists())

    def test_crc_failure_is_rejected(self):
        self.create_zip([('bueno.txt', 'correcto'), ('malo.txt', 'contenido-unico')])
        data = self.archive.read_bytes()
        self.archive.write_bytes(data.replace(b'contenido-unico', b'contenido-rotos', 1))
        self.assertEqual(self.run_script(self.archive, self.dest).returncode, 1)
        self.assertFalse(self.dest.exists())

    def test_relative_paths_starting_with_dash_and_uppercase_zip(self):
        self.create_zip([('-codigo.PY', '# pyside6\n')])
        archive = self.root / '-entrada.ZIP'
        self.archive.rename(archive)
        result = self.run_script('-entrada.ZIP', '-salida')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / '-salida/py/-codigo.PY').is_file())

    def test_grep_error_is_not_reported_as_no_match(self):
        self.create_zip([('main.py', 'import PySide6\n')])
        fakebin = self.root / 'bin'
        fakebin.mkdir()
        wrapper = fakebin / 'grep'
        real_grep = shutil.which('grep')
        wrapper.write_text('#!/usr/bin/env bash\n'
                           'for arg in "$@"; do [[ "$arg" != */main.py ]] || exit 2; done\n'
                           f'exec "{real_grep}" "$@"\n')
        wrapper.chmod(0o755)
        self.env['PATH'] = str(fakebin) + os.pathsep + os.environ['PATH']
        result = self.run_script(self.archive, self.dest)
        self.assertEqual(result.returncode, 1)
        self.assertIn('No se pudo analizar', result.stderr)
        self.assertNotIn('RESUMEN FINAL', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
