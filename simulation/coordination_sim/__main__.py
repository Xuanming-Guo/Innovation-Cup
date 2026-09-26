import sys

if len(sys.argv)>1 and sys.argv[1] in ('benchmark','generate','serve','benchmark-schemas','acceptance'):
    from .benchmark.cli import main
else:
    from .runner import main

raise SystemExit(main())
