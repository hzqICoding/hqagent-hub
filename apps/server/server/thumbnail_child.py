"""Standalone isolated decoder: no service imports, no network, no diagnostic text."""
import os
import io
import sys

def restrict():
    limit = 160 * 1024 * 1024
    if os.name == 'posix':
        import resource
        if sys.platform == 'darwin':
            # Do not rely on AS/DATA for decoder memory on Darwin: availability
            # and enforcement are not assumed here. No hard memory cap is claimed.
            # CPU seconds and regular-file size are additional best-effort guards;
            # FSIZE does not bound stdout (a pipe). The checks below still enforce
            # 40M pixels, first frame, 512px and 512KiB output; the parent enforces
            # an 8-second wall timeout and kills/waits for the actual decoder.
            for name, maximum in (('RLIMIT_CPU', 6), ('RLIMIT_FSIZE', 524288)):
                resource_id = getattr(resource, name, None)
                if resource_id is None:
                    continue
                try:
                    resource.setrlimit(resource_id, (maximum, maximum))
                except (ValueError, OSError):
                    # One unavailable kernel limit must not disable thumbnails
                    # or prevent trying the remaining independent limit.
                    continue
        else:
            # Linux/serverD retains mandatory 160MiB address-space, CPU and file
            # limits. Errors propagate: inability to install them is fail closed.
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
            resource.setrlimit(resource.RLIMIT_FSIZE, (524288, 524288))
    elif os.name == 'nt':
        # Windows keeps its mandatory per-process Job Object memory limit;
        # a failed setup remains fatal. The parent provides the same wall timeout.
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
