"""Media regressions for sideways phone zooms and sync across fractional-frame cuts.

STUDIO_RUN_MEDIA_TESTS=1 python -m unittest discover -s tests -p test_assembly_regression.py -v
Uses ffmpeg/ffprobe, standard-library Python, synthetic flashes and matching audio pulses.
No customer footage, models, credentials or existing Studio state are used.
"""
from array import array
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'video-studio/skills/video-studio/scripts'
FF = os.environ.get('STUDIO_TEST_FFMPEG') or shutil.which('ffmpeg')
FP = os.environ.get('STUDIO_TEST_FFPROBE') or shutil.which('ffprobe')
ASSEMBLY = Path(os.environ.get('STUDIO_TEST_ASSEMBLY') or SCRIPTS / 'assemble.py')


@unittest.skipUnless(os.environ.get('STUDIO_RUN_MEDIA_TESTS') == '1', 'enable the synthetic media regression suite explicitly')
class AssemblyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FF or not FP:
            raise RuntimeError('Media regressions require both ffmpeg and ffprobe.')
        cls.scratch = tempfile.TemporaryDirectory(prefix='studio-assembly-')
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.base = Path(cls.scratch.name)
        cls.state = cls.base / 'video-studio-codex'
        cls.state.mkdir()
        # Use an isolated valid platform record so the test also works with the
        # customer's downloaded static binaries even when they are not on PATH.
        os_name = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else 'linux'
        cls.env = dict(os.environ, VIDEO_STUDIO_STATE=str(cls.state), PYTHONPATH=str(SCRIPTS),
                       PYTHONDONTWRITEBYTECODE='1')
        cls.state.joinpath('.platform.json').write_text(json.dumps({
            'schema': 1, 'os': os_name, 'ffmpeg': str(FF), 'ffprobe': str(FP),
        }), encoding='utf-8')
        cls.source = cls.base / 'source with spaces.mp4'
        audio = cls.base / 'pulses.wav'
        samples = array('h')
        for index in range(12 * 48000):
            phase = index % 48000
            active = 24000 <= phase < 26400  # 50-ms tone, in sync with each white flash at x.500s
            samples.append(round(24000 * math.sin(2 * math.pi * 1000 * index / 48000)) if active else 0)
        if sys.byteorder != 'little':
            samples.byteswap()
        with wave.open(str(audio), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(samples.tobytes())
        cls.run_command([FF, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=320x180:r=30:d=12',
                         '-i', audio, '-vf', "drawbox=color=white:t=fill:enable='gte(mod(t,1),0.5)*lt(mod(t,1),0.6)'",
                         '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', cls.source])
        cls.display_rotation = '-display_rotation' in cls.run_command([FF, '-hide_banner', '-h', 'full'])

    @classmethod
    def run_command(cls, args, binary=False):
        result = subprocess.run([str(arg) for arg in args], env=cls.env, capture_output=True, timeout=240)
        if result.returncode:
            raise AssertionError('Command failed: ' + ' '.join(str(arg) for arg in args) + '\n' + result.stderr.decode('utf-8', 'replace')[-3000:])
        return result.stdout if binary else result.stdout.decode('utf-8')

    def assemble(self, name, source, edl):
        project = self.base / name
        project.mkdir()
        project.joinpath('sources.json').write_text(json.dumps({'c1': str(source)}), encoding='utf-8')
        project.joinpath('edl.json').write_text(json.dumps(edl), encoding='utf-8')
        self.run_command([sys.executable, '-B', ASSEMBLY, project])
        return project, json.loads(project.joinpath('segments.json').read_text(encoding='utf-8'))

    def test_sideways_phone_clips_allow_punch_in_zoom(self):
        for rotation in (90, 270):
            with self.subTest(rotation=rotation):
                rotated = self.base / f'phone-rotation-{rotation}.mp4'
                if self.display_rotation:
                    self.run_command([FF, '-y', '-v', 'error', '-display_rotation', str(rotation),
                                      '-i', self.source, '-c', 'copy', rotated])
                else:
                    self.run_command([FF, '-y', '-v', 'error', '-i', self.source, '-c', 'copy',
                                      '-metadata:s:v:0', f'rotate={rotation}', rotated])
                fixture = json.loads(self.run_command([FP, '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height:stream_tags=rotate:stream_side_data=rotation', '-of', 'json', rotated]))['streams'][0]
                actual_rotation = (fixture.get('tags') or {}).get('rotate') or next(
                    (side['rotation'] for side in fixture.get('side_data_list', []) if 'rotation' in side), 0)
                self.assertEqual(round(float(actual_rotation)) % 360, rotation)
                project, segments = self.assemble(f'zoom-{rotation}', rotated, [
                    {'id': 'zoom', 'clip': 'c1', 'in': .13, 'out': .73, 'zoom': 1.25, 'cx': .5, 'cy': .5}])
                self.assertEqual((segments[0]['src_w'], segments[0]['src_h']), (180, 320))
                metadata = json.loads(self.run_command([FP, '-v', 'error', '-select_streams', 'v:0',
                     '-show_entries', 'stream=width,height', '-of', 'json', project / 'assets/aroll.mp4']))
                stream = metadata['streams'][0]
                self.assertEqual((stream['width'], stream['height']), (1080, 1920))

    def test_lip_sync_remains_within_ten_ms_across_twelve_cuts(self):
        durations = [.413, .517, .623, .707, .439, .541, .655, .763, .467, .583, .691, .791]
        edl = [{'id': f'cut-{index}', 'clip': 'c1', 'in': index + .13, 'out': index + .13 + duration}
               for index, duration in enumerate(durations)]
        project, segments = self.assemble('twelve-cuts', self.source, edl)
        output = project / 'assets/aroll.mp4'
        pixels = self.run_command([FF, '-v', 'error', '-i', output, '-vf', 'scale=1:1:flags=area,format=gray',
                                  '-an', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], binary=True)
        visual_times = [index / 30 for index, level in enumerate(pixels)
                        if level > 200 and (index == 0 or pixels[index - 1] <= 200)]
        pcm = self.run_command([FF, '-v', 'error', '-i', output, '-vn', '-ac', '1', '-ar', '48000',
                               '-f', 's16le', '-'], binary=True)
        samples = array('h')
        samples.frombytes(pcm)
        if sys.byteorder != 'little':
            samples.byteswap()
        starts, previous = [], -48000
        for index, value in enumerate(samples):
            if abs(value) < 7000:
                continue
            if index - previous > 2400:
                starts.append(index / 48000)
            previous = index
        self.assertEqual(len(visual_times), 12, f'Visual landmarks: {visual_times}')
        self.assertEqual(len(starts), 12, f'Audio landmarks: {starts}')
        offsets = [(audio - video) * 1000 for audio, video in zip(starts, visual_times)]
        print('\nAudio minus video landmark offsets (ms): ' + ', '.join(f'{offset:.3f}' for offset in offsets), flush=True)
        self.assertLessEqual(max(abs(offset) for offset in offsets), 10, offsets)
        self.assertLessEqual(abs(offsets[-1] - offsets[0]), 10, offsets)
        # The intermediate PCM duration must match the actual frame count, not
        # just the requested fractional-frame EDL duration.
        for index, segment in enumerate(segments):
            meta = json.loads(self.run_command([FP, '-v', 'error', '-select_streams', 'a:0',
                '-show_entries', 'stream=duration_ts,time_base', '-of', 'json', project / f'work/seg_{index}.mp4']))
            stream = meta['streams'][0]
            numerator, denominator = (int(part) for part in stream['time_base'].split('/'))
            duration = int(stream['duration_ts']) * numerator / denominator
            self.assertAlmostEqual(duration, segment['frames'] / 30, delta=1 / 48000)

    def test_early_source_end_keeps_audio_matched_to_available_video(self):
        project, segments = self.assemble('early-source-end', self.source, [
            {'id': 'tail', 'clip': 'c1', 'in': 11.83, 'out': 12.33}])
        self.assertGreater(segments[0]['frames'], 0)
        self.assertLess(segments[0]['frames'], 15)
        meta = json.loads(self.run_command([FP, '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=duration_ts,time_base', '-of', 'json', project / 'work/seg_0.mp4']))
        stream = meta['streams'][0]
        numerator, denominator = (int(part) for part in stream['time_base'].split('/'))
        self.assertAlmostEqual(int(stream['duration_ts']) * numerator / denominator,
                               segments[0]['frames'] / 30, delta=1 / 48000)


if __name__ == '__main__':
    unittest.main()
