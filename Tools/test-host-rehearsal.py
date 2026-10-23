"""run-all-tests entry for Tools/rehearse-overlays.py (stream-day overlay rehearsal in a sim Host). Usage: python Tools/test-host-rehearsal.py [dll]"""
import os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.exit(subprocess.call([sys.executable, os.path.join(here, 'rehearse-overlays.py')] + sys.argv[1:]))
