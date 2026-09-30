"""Standalone isolated decoder: no service imports, no network, no diagnostic text."""
import os
import io
import sys

def restrict():
    limit = 160 * 1024 * 1024
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
        resource.setrlimit(resource.RLIMIT_FSIZE, (524288, 524288))
    elif os.name == 'nt':
        import ctypes
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ('perProcess', ctypes.c_longlong),
                ('perJob', ctypes.c_longlong),
                ('flags', w.DWORD),
                ('min', ctypes.c_size_t),
                ('max', ctypes.c_size_t),
                ('active', w.DWORD),
                ('affinity', ctypes.c_size_t),
                ('priority', w.DWORD),
                ('scheduling', w.DWORD)
            ]

        class IO(ctypes.Structure):
            _fields_ = [(s, ctypes.c_ulonglong) for s in ('readOps', 'writeOps', 'otherOps', 'readBytes', 'writeBytes', 'otherBytes')]

        class Extended(ctypes.Structure):
            _fields_ = [
                ('basic', Basic),
                ('io', IO),
                ('processMemory', ctypes.c_size_t),
                ('jobMemory', ctypes.c_size_t),
                ('peakProcess', ctypes.c_size_t),
                ('peakJob', ctypes.c_size_t)
            ]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.GetCurrentProcess.restype = w.HANDLE
        job = kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 256
        info.processMemory = limit
        if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or (not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())):
            raise RuntimeError()
    else:
        raise RuntimeError()
if __name__ == '__main__':
    try:
        restrict()
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 40000000
        with Image.open(sys.argv[1], formats=('JPEG', 'PNG', 'GIF', 'WEBP')) as image:
            if image.width * image.height > 40000000:
                raise ValueError()
            image.seek(0)
            image.thumbnail((512, 512))
            clean = Image.new('RGBA', image.size)
            clean.paste(image.convert('RGBA'))
            output = io.BytesIO()
            clean.save(output, format='PNG')
        if output.tell() > 524288:
            raise ValueError()
        sys.stdout.buffer.write(output.getvalue())
    except BaseException:
        sys.exit(1)
