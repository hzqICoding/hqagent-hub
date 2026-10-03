"""Frozen executable bootstrap; imports only the installed Hub entry point."""
import multiprocessing

from runtime.main import main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
